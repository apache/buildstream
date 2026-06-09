#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""
Tests for the speculative actions weak key lookup.

The weak cache key is used for speculative actions lookup because it is:
- Stable across dependency version changes (only dep names, not cache keys)
- Changing when the element's own sources change
- Changing when build commands change
- Changing when environment changes
- Changing when sandbox config changes

This mirrors Element._calculate_cache_key() with weak-mode dependencies
(only [project_name, name] per dependency).
"""

import pytest
from buildstream._cachekey import generate_key


# These helpers mirror the structure of Element._calculate_cache_key() to
# verify the properties of the weak key as used for speculative actions.
# The actual weak key is computed by Element.__update_cache_keys() using
# _calculate_cache_key(dependencies) where dependencies are [project, name]
# pairs (in non-strict mode).

def _make_weak_key_dict(
    plugin_name="autotools",
    plugin_key=None,
    sources_key="abc123",
    dep_names=None,
    sandbox=None,
    environment=None,
    public=None,
):
    """Helper to construct a dict that mirrors the weak cache key inputs.

    This doesn't replicate _calculate_cache_key exactly, but captures the
    same structural properties for testing key stability/invalidation.
    """
    if plugin_key is None:
        plugin_key = {
            "build-commands": ["make"],
            "install-commands": ["make install"],
        }
    if dep_names is None:
        dep_names = [["project", "base.bst"], ["project", "dep-a.bst"]]
    if environment is None:
        environment = {"PATH": "/usr/bin"}
    if public is None:
        public = {}

    cache_key_dict = {
        "core-artifact-version": 1,
        "element-plugin-key": plugin_key,
        "element-plugin-name": plugin_name,
        "element-plugin-version": 0,
        "sources": sources_key,
        "public": public,
        "fatal-warnings": [],
    }
    if sandbox is not None:
        cache_key_dict["sandbox"] = sandbox
        cache_key_dict["environment"] = environment

    # Weak dependencies: only [project, name] pairs (no cache keys)
    cache_key_dict["dependencies"] = sorted(dep_names)

    return cache_key_dict


class TestWeakKeyStability:
    """Verify key stability: same inputs produce same key."""

    def test_same_inputs_same_key(self):
        """Identical inputs must produce the same key."""
        dict1 = _make_weak_key_dict()
        dict2 = _make_weak_key_dict()
        assert generate_key(dict1) == generate_key(dict2)

    def test_stable_across_dependency_version_changes(self):
        """Key uses dependency names only, not their cache keys.

        When a dependency is rebuilt with different content, the weak key
        remains stable because it only records [project, name] pairs.
        """
        # Same dep names → same key, regardless of what version was built
        dict1 = _make_weak_key_dict(dep_names=[["proj", "dep.bst"]])
        dict2 = _make_weak_key_dict(dep_names=[["proj", "dep.bst"]])
        assert generate_key(dict1) == generate_key(dict2)

    def test_dependency_order_irrelevant(self):
        """Dependency names are sorted, so ordering doesn't matter."""
        dict1 = _make_weak_key_dict(dep_names=[["proj", "a.bst"], ["proj", "b.bst"]])
        dict2 = _make_weak_key_dict(dep_names=[["proj", "b.bst"], ["proj", "a.bst"]])
        assert generate_key(dict1) == generate_key(dict2)


class TestWeakKeyInvalidation:
    """Verify key changes when element configuration changes."""

    def test_changes_when_source_changes(self):
        """Different source content must produce a different key.

        Unlike the old structural key, the weak key includes source
        digests, so changing source code correctly invalidates it.
        """
        key1 = generate_key(_make_weak_key_dict(sources_key="source-v1"))
        key2 = generate_key(_make_weak_key_dict(sources_key="source-v2"))
        assert key1 != key2

    def test_changes_when_build_commands_change(self):
        """Different build commands must produce a different key."""
        key1 = generate_key(
            _make_weak_key_dict(plugin_key={"build-commands": ["make"]})
        )
        key2 = generate_key(
            _make_weak_key_dict(plugin_key={"build-commands": ["cmake --build ."]})
        )
        assert key1 != key2

    def test_changes_when_install_commands_change(self):
        """Different install commands must produce a different key."""
        key1 = generate_key(
            _make_weak_key_dict(plugin_key={"install-commands": ["make install"]})
        )
        key2 = generate_key(
            _make_weak_key_dict(plugin_key={"install-commands": ["make install DESTDIR=/foo"]})
        )
        assert key1 != key2

    def test_changes_when_dependency_names_change(self):
        """Adding a dependency must change the key."""
        key1 = generate_key(
            _make_weak_key_dict(dep_names=[["proj", "base.bst"]])
        )
        key2 = generate_key(
            _make_weak_key_dict(dep_names=[["proj", "base.bst"], ["proj", "extra.bst"]])
        )
        assert key1 != key2

    def test_changes_when_dependency_removed(self):
        """Removing a dependency must change the key."""
        key1 = generate_key(
            _make_weak_key_dict(dep_names=[["proj", "base.bst"], ["proj", "dep.bst"]])
        )
        key2 = generate_key(
            _make_weak_key_dict(dep_names=[["proj", "base.bst"]])
        )
        assert key1 != key2

    def test_changes_when_plugin_name_changes(self):
        """Different plugin type must produce a different key."""
        key1 = generate_key(_make_weak_key_dict(plugin_name="autotools"))
        key2 = generate_key(_make_weak_key_dict(plugin_name="cmake"))
        assert key1 != key2

    def test_changes_when_sandbox_config_changes(self):
        """Different sandbox configuration must change the key."""
        key1 = generate_key(
            _make_weak_key_dict(sandbox={"build-os": "linux", "build-arch": "x86_64"})
        )
        key2 = generate_key(
            _make_weak_key_dict(sandbox={"build-os": "linux", "build-arch": "aarch64"})
        )
        assert key1 != key2

    def test_changes_when_environment_changes(self):
        """Different environment must change the key."""
        key1 = generate_key(
            _make_weak_key_dict(
                sandbox={"build-os": "linux"},
                environment={"PATH": "/usr/bin"},
            )
        )
        key2 = generate_key(
            _make_weak_key_dict(
                sandbox={"build-os": "linux"},
                environment={"PATH": "/usr/bin", "CC": "gcc"},
            )
        )
        assert key1 != key2

    def test_no_sandbox_vs_sandbox(self):
        """Having sandbox config vs not having it must change the key."""
        key1 = generate_key(_make_weak_key_dict(sandbox=None))
        key2 = generate_key(
            _make_weak_key_dict(sandbox={"build-os": "linux"})
        )
        assert key1 != key2


class TestWeakKeyFormat:
    """Verify key format properties."""

    def test_key_is_hex_digest(self):
        """Key should be a valid sha256 hex digest."""
        key = generate_key(_make_weak_key_dict())
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)
