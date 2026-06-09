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
Unit tests for SpeculativeActionInstantiator.

Given overlays and new file digests, verify correct digest replacements
in action input trees. No sandbox needed.
"""

import hashlib
import pytest

from buildstream._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from buildstream._protos.buildstream.v2 import speculative_actions_pb2


def _make_digest(content):
    """Create a Digest proto from content bytes."""
    digest = remote_execution_pb2.Digest()
    digest.hash = hashlib.sha256(content).hexdigest()
    digest.size_bytes = len(content)
    return digest


class FakeCAS:
    """In-memory CAS for testing."""

    def __init__(self):
        self._blobs = {}
        self._directories = {}
        self._actions = {}

    def store_directory_proto(self, directory):
        data = directory.SerializeToString()
        digest = _make_digest(data)
        self._directories[digest.hash] = directory
        self._blobs[digest.hash] = data
        return digest

    def fetch_directory_proto(self, digest):
        return self._directories.get(digest.hash)

    def store_action(self, action):
        data = action.SerializeToString()
        digest = _make_digest(data)
        self._actions[digest.hash] = action
        self._blobs[digest.hash] = data
        return digest

    def fetch_action(self, digest):
        return self._actions.get(digest.hash)

    def store_proto(self, proto):
        data = proto.SerializeToString()
        return _make_digest(data)

    def fetch_proto(self, digest, proto_class):
        data = self._blobs.get(digest.hash)
        if data is None:
            return None
        proto = proto_class()
        proto.ParseFromString(data)
        return proto


class FakeSourceDir:
    def __init__(self, digest):
        self._digest = digest

    def _get_digest(self):
        return self._digest


class FakeSources:
    def __init__(self, files_dir):
        self._files_dir = files_dir
        self._cached = True

    def cached(self):
        return self._cached

    def get_files(self):
        return self._files_dir


class FakeArtifact:
    def __init__(self, files_dir=None, is_cached=True, proto=None):
        self._files_dir = files_dir
        self._cached = is_cached
        self._proto = proto

    def cached(self):
        return self._cached

    def get_files(self):
        return self._files_dir

    def _get_proto(self):
        return self._proto


class FakeArtifactCache:
    def __init__(self):
        self._spec_actions = {}

    def get_speculative_actions(self, artifact, structural_key=None):
        return self._spec_actions.get(id(artifact))

    def store_speculative_actions(self, artifact, spec_actions, structural_key=None):
        self._spec_actions[id(artifact)] = spec_actions


class FakeElement:
    def __init__(self, name, sources=None, artifact=None, project_name="project"):
        self.name = name
        self.project_name = project_name
        self._Element__sources = sources
        self._artifact = artifact

    def sources(self):
        if self._Element__sources:
            yield True

    def _cached(self):
        return self._artifact is not None and self._artifact.cached()

    def _get_artifact(self):
        return self._artifact

    def _dependencies(self, scope, recurse=False):
        return []

    def _get_cache_key(self):
        return "fake-cache-key"

    def info(self, msg):
        pass

    def warn(self, msg):
        pass


def _build_source_tree(cas, files):
    """Build a CAS directory tree from a dict of {path: content_bytes}."""
    dirs = {}
    for path, content in files.items():
        parts = path.rsplit("/", 1)
        if len(parts) == 1:
            dirname, filename = "", parts[0]
        else:
            dirname, filename = parts
        dirs.setdefault(dirname, []).append((filename, content))

    dir_digests = {}
    all_dirs = set()
    for path in files:
        parts = path.split("/")
        for i in range(len(parts) - 1):
            all_dirs.add("/".join(parts[: i + 1]))
    all_dirs.add("")

    # Process deepest directories first, root ("") always last
    non_root = sorted((d for d in all_dirs if d), key=lambda d: -d.count("/"))
    non_root.append("")

    for dirpath in non_root:
        directory = remote_execution_pb2.Directory()
        for filename, content in dirs.get(dirpath, []):
            file_node = directory.files.add()
            file_node.name = filename
            file_node.digest.CopyFrom(_make_digest(content))

        for child_dir, child_digest in sorted(dir_digests.items()):
            if dirpath == "":
                if "/" not in child_dir:
                    dir_node = directory.directories.add()
                    dir_node.name = child_dir
                    dir_node.digest.CopyFrom(child_digest)
            else:
                prefix = dirpath + "/"
                if child_dir.startswith(prefix) and "/" not in child_dir[len(prefix) :]:
                    dir_node = directory.directories.add()
                    dir_node.name = child_dir[len(prefix) :]
                    dir_node.digest.CopyFrom(child_digest)

        digest = cas.store_directory_proto(directory)
        dir_digests[dirpath] = digest

    return dir_digests[""]


class TestInstantiatorDigestReplacement:
    """Test that Instantiator correctly replaces digests in action trees."""

    def test_replaces_source_digest(self):
        """SOURCE overlay should replace old digest with current source digest."""
        from buildstream._speculative_actions.instantiator import SpeculativeActionInstantiator

        cas = FakeCAS()
        artifactcache = FakeArtifactCache()

        old_content = b'old source content'
        new_content = b'new source content'
        old_digest = _make_digest(old_content)
        new_digest = _make_digest(new_content)

        # Build the original action input tree with old content
        input_root = _build_source_tree(cas, {"main.c": old_content})
        action = remote_execution_pb2.Action()
        action.input_root_digest.CopyFrom(input_root)
        action_digest = cas.store_action(action)

        # Build current source tree with new content
        new_source_root = _build_source_tree(cas, {"main.c": new_content})
        sources = FakeSources(FakeSourceDir(new_source_root))
        element = FakeElement("test.bst", sources=sources)

        # Create a SpeculativeAction with SOURCE overlay
        spec_action = speculative_actions_pb2.SpeculativeActions.SpeculativeAction()
        spec_action.base_action_digest.CopyFrom(action_digest)
        overlay = spec_action.overlays.add()
        overlay.type = speculative_actions_pb2.SpeculativeActions.Overlay.SOURCE
        overlay.source_element = ""  # self
        overlay.source_path = "main.c"
        overlay.target_digest.CopyFrom(old_digest)

        instantiator = SpeculativeActionInstantiator(cas, artifactcache)
        result_digest = instantiator.instantiate_action(spec_action, element, {})

        assert result_digest is not None
        # The result should be a new action (different digest since content changed)
        assert result_digest.hash != action_digest.hash

        # Verify the new action has the updated input tree
        new_action = cas.fetch_action(result_digest)
        assert new_action is not None
        new_root = cas.fetch_directory_proto(new_action.input_root_digest)
        assert new_root is not None
        assert len(new_root.files) == 1
        assert new_root.files[0].digest.hash == new_digest.hash

    def test_unchanged_digest_returns_base(self):
        """When no digests actually change, return the base action digest."""
        from buildstream._speculative_actions.instantiator import SpeculativeActionInstantiator

        cas = FakeCAS()
        artifactcache = FakeArtifactCache()

        content = b'same content'
        digest = _make_digest(content)

        input_root = _build_source_tree(cas, {"main.c": content})
        action = remote_execution_pb2.Action()
        action.input_root_digest.CopyFrom(input_root)
        action_digest = cas.store_action(action)

        # Sources have the same content
        source_root = _build_source_tree(cas, {"main.c": content})
        sources = FakeSources(FakeSourceDir(source_root))
        element = FakeElement("test.bst", sources=sources)

        spec_action = speculative_actions_pb2.SpeculativeActions.SpeculativeAction()
        spec_action.base_action_digest.CopyFrom(action_digest)
        overlay = spec_action.overlays.add()
        overlay.type = speculative_actions_pb2.SpeculativeActions.Overlay.SOURCE
        overlay.source_element = ""
        overlay.source_path = "main.c"
        overlay.target_digest.CopyFrom(digest)

        instantiator = SpeculativeActionInstantiator(cas, artifactcache)
        result_digest = instantiator.instantiate_action(spec_action, element, {})

        # Should return the base action digest (no modifications)
        assert result_digest.hash == action_digest.hash

    def test_missing_base_action_returns_none(self):
        """If the base action can't be fetched, return None."""
        from buildstream._speculative_actions.instantiator import SpeculativeActionInstantiator

        cas = FakeCAS()
        artifactcache = FakeArtifactCache()

        # Create a digest for a non-existent action
        fake_digest = _make_digest(b'does-not-exist')

        spec_action = speculative_actions_pb2.SpeculativeActions.SpeculativeAction()
        spec_action.base_action_digest.CopyFrom(fake_digest)

        element = FakeElement("test.bst")
        instantiator = SpeculativeActionInstantiator(cas, artifactcache)
        result = instantiator.instantiate_action(spec_action, element, {})

        assert result is None

    def test_replaces_in_nested_directories(self):
        """Digests in nested directory trees should be replaced."""
        from buildstream._speculative_actions.instantiator import SpeculativeActionInstantiator

        cas = FakeCAS()
        artifactcache = FakeArtifactCache()

        old_content = b'old nested file'
        new_content = b'new nested file'
        old_digest = _make_digest(old_content)
        new_digest = _make_digest(new_content)

        # Build nested input tree
        input_root = _build_source_tree(cas, {"src/lib/util.c": old_content})
        action = remote_execution_pb2.Action()
        action.input_root_digest.CopyFrom(input_root)
        action_digest = cas.store_action(action)

        # New sources with updated content
        source_root = _build_source_tree(cas, {"lib/util.c": new_content})
        sources = FakeSources(FakeSourceDir(source_root))
        element = FakeElement("test.bst", sources=sources)

        spec_action = speculative_actions_pb2.SpeculativeActions.SpeculativeAction()
        spec_action.base_action_digest.CopyFrom(action_digest)
        overlay = spec_action.overlays.add()
        overlay.type = speculative_actions_pb2.SpeculativeActions.Overlay.SOURCE
        overlay.source_element = ""
        overlay.source_path = "lib/util.c"
        overlay.target_digest.CopyFrom(old_digest)

        instantiator = SpeculativeActionInstantiator(cas, artifactcache)
        result_digest = instantiator.instantiate_action(spec_action, element, {})

        assert result_digest is not None
        assert result_digest.hash != action_digest.hash

    def test_multiple_overlays_applied(self):
        """Multiple overlays should all be applied to the same action."""
        from buildstream._speculative_actions.instantiator import SpeculativeActionInstantiator

        cas = FakeCAS()
        artifactcache = FakeArtifactCache()

        old_a = b'old a.c'
        old_b = b'old b.c'
        new_a = b'new a.c'
        new_b = b'new b.c'

        input_root = _build_source_tree(cas, {"a.c": old_a, "b.c": old_b})
        action = remote_execution_pb2.Action()
        action.input_root_digest.CopyFrom(input_root)
        action_digest = cas.store_action(action)

        source_root = _build_source_tree(cas, {"a.c": new_a, "b.c": new_b})
        sources = FakeSources(FakeSourceDir(source_root))
        element = FakeElement("test.bst", sources=sources)

        spec_action = speculative_actions_pb2.SpeculativeActions.SpeculativeAction()
        spec_action.base_action_digest.CopyFrom(action_digest)

        overlay_a = spec_action.overlays.add()
        overlay_a.type = speculative_actions_pb2.SpeculativeActions.Overlay.SOURCE
        overlay_a.source_element = ""
        overlay_a.source_path = "a.c"
        overlay_a.target_digest.CopyFrom(_make_digest(old_a))

        overlay_b = spec_action.overlays.add()
        overlay_b.type = speculative_actions_pb2.SpeculativeActions.Overlay.SOURCE
        overlay_b.source_element = ""
        overlay_b.source_path = "b.c"
        overlay_b.target_digest.CopyFrom(_make_digest(old_b))

        instantiator = SpeculativeActionInstantiator(cas, artifactcache)
        result_digest = instantiator.instantiate_action(spec_action, element, {})

        assert result_digest is not None
        assert result_digest.hash != action_digest.hash

        # Verify both files were replaced
        new_action = cas.fetch_action(result_digest)
        new_root = cas.fetch_directory_proto(new_action.input_root_digest)
        file_hashes = {f.name: f.digest.hash for f in new_root.files}
        assert file_hashes["a.c"] == _make_digest(new_a).hash
        assert file_hashes["b.c"] == _make_digest(new_b).hash


class TestInstantiatorArtifactOverlay:
    """Test ARTIFACT overlay resolution."""

    def test_resolves_artifact_overlay_from_dep(self):
        """ARTIFACT overlay should resolve file digest from dependency artifact."""
        from buildstream._speculative_actions.instantiator import SpeculativeActionInstantiator

        cas = FakeCAS()
        artifactcache = FakeArtifactCache()

        old_lib = b'old-lib-content'
        new_lib = b'new-lib-content'
        old_digest = _make_digest(old_lib)
        new_digest = _make_digest(new_lib)

        # Build original action
        input_root = _build_source_tree(cas, {"lib/libfoo.so": old_lib})
        action = remote_execution_pb2.Action()
        action.input_root_digest.CopyFrom(input_root)
        action_digest = cas.store_action(action)

        # Dependency element with updated artifact
        dep_artifact_root = _build_source_tree(cas, {"lib/libfoo.so": new_lib})
        dep_artifact = FakeArtifact(FakeSourceDir(dep_artifact_root))
        dep_element = FakeElement("dep.bst", artifact=dep_artifact)

        element = FakeElement("test.bst")
        element_lookup = {"dep.bst": dep_element}

        spec_action = speculative_actions_pb2.SpeculativeActions.SpeculativeAction()
        spec_action.base_action_digest.CopyFrom(action_digest)
        overlay = spec_action.overlays.add()
        overlay.type = speculative_actions_pb2.SpeculativeActions.Overlay.ARTIFACT
        overlay.source_element = "dep.bst"
        overlay.source_path = "lib/libfoo.so"
        overlay.target_digest.CopyFrom(old_digest)

        instantiator = SpeculativeActionInstantiator(cas, artifactcache)
        result_digest = instantiator.instantiate_action(spec_action, element, element_lookup)

        assert result_digest is not None
        assert result_digest.hash != action_digest.hash
