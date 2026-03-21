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
Pipeline integration tests for speculative actions.

These tests exercise the full generate → store → retrieve → instantiate
pipeline using in-memory fakes for CAS and artifact cache. No sandbox
or real trexe binary needed — subaction digests are constructed directly
from proto objects.

The scenario modeled:
  1. "Build" an element by constructing Action protos with known input trees
  2. Run the Generator to produce SpeculativeActions from those subactions
  3. Store SpeculativeActions via the artifact cache (weak key path)
  4. Simulate a source change (new file content)
  5. Retrieve SpeculativeActions and run the Instantiator
  6. Verify the instantiated action has the updated file digests
"""

import hashlib
import os
import tempfile
import pytest

from buildstream._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from buildstream._protos.buildstream.v2 import speculative_actions_pb2
from buildstream._speculative_actions.generator import SpeculativeActionsGenerator
from buildstream._speculative_actions.instantiator import SpeculativeActionInstantiator


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

def _make_digest(content):
    """Create a Digest proto from content bytes."""
    digest = remote_execution_pb2.Digest()
    digest.hash = hashlib.sha256(content).hexdigest()
    digest.size_bytes = len(content)
    return digest


class FakeCAS:
    """In-memory CAS that supports the operations used by generator and instantiator."""

    def __init__(self):
        self._blobs = {}       # hash -> bytes
        self._directories = {} # hash -> Directory proto
        self._actions = {}     # hash -> Action proto

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
        digest = _make_digest(data)
        self._blobs[digest.hash] = data
        return digest

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


class FakeArtifactProto:
    """Minimal artifact proto supporting HasField and speculative_actions."""

    def __init__(self):
        self._speculative_actions = None
        self.build_deps = []

    def HasField(self, name):
        if name == "speculative_actions":
            return self._speculative_actions is not None
        return False

    @property
    def speculative_actions(self):
        return self._speculative_actions

    @speculative_actions.setter
    def speculative_actions(self, value):
        self._speculative_actions = value


class FakeArtifact:
    def __init__(self, files_dir=None, is_cached=True, element=None):
        self._files_dir = files_dir
        self._cached = is_cached
        self._element = element

    def cached(self):
        return self._cached

    def get_files(self):
        return self._files_dir

    def _get_proto(self):
        return None

    def get_extract_key(self):
        return "extract-key"


class FakeProject:
    def __init__(self, name="test-project"):
        self.name = name


class FakeElement:
    def __init__(self, name, sources=None, artifact=None, project_name="project"):
        self.name = name
        self.project_name = project_name
        self._Element__sources = sources
        self._artifact = artifact
        self._project = FakeProject()

    def sources(self):
        if self._Element__sources:
            yield True

    def _cached(self):
        return self._artifact is not None and self._artifact.cached()

    def _get_artifact(self):
        return self._artifact

    def _get_project(self):
        return self._project

    def _dependencies(self, scope, recurse=False):
        return []

    def _get_cache_key(self):
        return "fake-cache-key"

    def get_artifact_name(self, key):
        return "{}/{}/{}".format(self._project.name, self.name, key)

    def info(self, msg):
        pass

    def warn(self, msg):
        pass


def _build_source_tree(cas, files):
    """Build a CAS directory tree from {path: content_bytes}, return root Digest."""
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
                if child_dir.startswith(prefix) and "/" not in child_dir[len(prefix):]:
                    dir_node = directory.directories.add()
                    dir_node.name = child_dir[len(prefix):]
                    dir_node.digest.CopyFrom(child_digest)

        digest = cas.store_directory_proto(directory)
        dir_digests[dirpath] = digest

    return dir_digests[""]


def _build_action(cas, input_root_digest):
    """Build an Action proto with the given input root, store it, return Digest."""
    action = remote_execution_pb2.Action()
    action.input_root_digest.CopyFrom(input_root_digest)
    return cas.store_action(action)


class FakeArtifactCache:
    """Artifact cache backed by a temp directory, using real file paths like the production code."""

    def __init__(self, cas, basedir):
        self.cas = cas
        self._basedir = basedir
        self._by_artifact = {}  # id(artifact) -> SpeculativeActions

    def store_speculative_actions(self, artifact, spec_actions, weak_key=None):
        # Store proto in CAS
        spec_actions_digest = self.cas.store_proto(spec_actions)

        # Store by artifact identity (for get_speculative_actions without weak_key)
        self._by_artifact[id(artifact)] = spec_actions

        # Store weak key reference
        if weak_key:
            element = artifact._element
            project = element._get_project()
            sa_ref = "{}/{}/speculative-{}".format(project.name, element.name, weak_key)
            sa_ref_path = os.path.join(self._basedir, sa_ref)
            os.makedirs(os.path.dirname(sa_ref_path), exist_ok=True)
            with open(sa_ref_path, mode="w+b") as f:
                f.write(spec_actions.SerializeToString())

    def get_speculative_actions(self, artifact, weak_key=None):
        if weak_key is not None:
            if not weak_key:
                return None
            element = artifact._element
            project = element._get_project()
            sa_ref = "{}/{}/speculative-{}".format(project.name, element.name, weak_key)
            sa_ref_path = os.path.join(self._basedir, sa_ref)
            if os.path.exists(sa_ref_path):
                spec_actions = speculative_actions_pb2.SpeculativeActions()
                with open(sa_ref_path, mode="r+b") as f:
                    spec_actions.ParseFromString(f.read())
                return spec_actions
            return None

        # No weak_key provided: lookup by artifact identity
        # (used by _seed_dependency_outputs which passes just the artifact)
        return self._by_artifact.get(id(artifact))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGenerateStoreRetrieveInstantiate:
    """Full pipeline: generate overlays, store, retrieve, instantiate with changed sources."""

    def test_source_change_roundtrip(self, tmp_path):
        """
        Scenario: element has source file main.c. A build records a subaction
        whose input tree contains main.c. After the build, we generate and
        store SpeculativeActions. Later, main.c changes. We retrieve the
        stored SA and instantiate — the action's input tree should now
        reference the new main.c digest.
        """
        cas = FakeCAS()
        artifactcache = FakeArtifactCache(cas, str(tmp_path))

        # --- Build phase (v1) ---
        v1_content = b'int main() { return 0; }'
        v1_digest = _make_digest(v1_content)

        # Element sources contain main.c v1
        source_root_v1 = _build_source_tree(cas, {"main.c": v1_content})
        sources_v1 = FakeSources(FakeSourceDir(source_root_v1))

        element = FakeElement("app.bst", sources=sources_v1)

        # The build produced a subaction whose input tree includes main.c
        subaction_input = _build_source_tree(cas, {"main.c": v1_content})
        subaction_digest = _build_action(cas, subaction_input)

        # --- Generate phase ---
        generator = SpeculativeActionsGenerator(cas)
        spec_actions = generator.generate_speculative_actions(element, [subaction_digest], [])

        assert len(spec_actions.actions) == 1
        assert len(spec_actions.actions[0].overlays) == 1
        overlay = spec_actions.actions[0].overlays[0]
        assert overlay.type == speculative_actions_pb2.SpeculativeActions.Overlay.SOURCE
        assert overlay.source_path == "main.c"
        assert overlay.target_digest.hash == v1_digest.hash

        # --- Store phase ---
        weak_key = "fake-weak-key-v1"
        artifact = FakeArtifact(element=element)
        artifactcache.store_speculative_actions(artifact, spec_actions, weak_key=weak_key)

        # --- Source change (v2) ---
        v2_content = b'int main() { return 42; }'
        v2_digest = _make_digest(v2_content)
        source_root_v2 = _build_source_tree(cas, {"main.c": v2_content})
        sources_v2 = FakeSources(FakeSourceDir(source_root_v2))

        # New element state with updated sources (same weak key because
        # in real life, the weak key for downstream elements is stable
        # across dependency version changes — here we're the leaf element
        # whose source changed, so in practice this SA would be stored
        # under a *different* weak key. But the retrieve+instantiate
        # logic is the same.)
        element_v2 = FakeElement("app.bst", sources=sources_v2)
        artifact_v2 = FakeArtifact(element=element_v2)

        # --- Retrieve phase ---
        retrieved = artifactcache.get_speculative_actions(artifact_v2, weak_key=weak_key)
        assert retrieved is not None
        assert len(retrieved.actions) == 1

        # --- Instantiate phase ---
        instantiator = SpeculativeActionInstantiator(cas, artifactcache)
        result_digest = instantiator.instantiate_action(retrieved.actions[0], element_v2, {})

        assert result_digest is not None
        # The action should be different (new input digest)
        assert result_digest.hash != subaction_digest.hash

        # Verify the new action's input tree has main.c with v2 content digest
        new_action = cas.fetch_action(result_digest)
        assert new_action is not None
        new_root = cas.fetch_directory_proto(new_action.input_root_digest)
        assert new_root is not None
        assert len(new_root.files) == 1
        assert new_root.files[0].name == "main.c"
        assert new_root.files[0].digest.hash == v2_digest.hash

    def test_dependency_artifact_change_roundtrip(self, tmp_path):
        """
        Scenario: element depends on dep.bst whose artifact provides libfoo.so.
        A build records a subaction using both main.c (source) and libfoo.so
        (from dep). After storing SA, dep.bst is rebuilt with new libfoo.so.
        Instantiation should produce an action with the new libfoo.so digest.
        """
        cas = FakeCAS()
        artifactcache = FakeArtifactCache(cas, str(tmp_path))

        # --- Build phase (v1) ---
        src_content = b'#include "foo.h"\nint main() { foo(); }'
        lib_v1 = b'libfoo-v1-content'
        lib_v1_digest = _make_digest(lib_v1)

        # Element sources
        source_root = _build_source_tree(cas, {"main.c": src_content})
        sources = FakeSources(FakeSourceDir(source_root))

        # Dependency artifact with libfoo.so v1
        dep_artifact_root_v1 = _build_source_tree(cas, {"lib/libfoo.so": lib_v1})
        dep_artifact_v1 = FakeArtifact(FakeSourceDir(dep_artifact_root_v1))
        dep_element_v1 = FakeElement("dep.bst", artifact=dep_artifact_v1)

        element = FakeElement("app.bst", sources=sources)

        # Subaction input tree has both source file and dep library
        subaction_input = _build_source_tree(cas, {
            "main.c": src_content,
            "lib/libfoo.so": lib_v1,
        })
        subaction_digest = _build_action(cas, subaction_input)

        # --- Generate ---
        generator = SpeculativeActionsGenerator(cas)
        spec_actions = generator.generate_speculative_actions(
            element, [subaction_digest], [dep_element_v1]
        )

        assert len(spec_actions.actions) == 1
        overlays = spec_actions.actions[0].overlays
        overlay_types = {o.type for o in overlays}
        assert speculative_actions_pb2.SpeculativeActions.Overlay.SOURCE in overlay_types
        assert speculative_actions_pb2.SpeculativeActions.Overlay.ARTIFACT in overlay_types

        # --- Store ---
        weak_key = "fake-weak-key-app"
        artifact = FakeArtifact(element=element)
        artifactcache.store_speculative_actions(artifact, spec_actions, weak_key=weak_key)

        # --- Dependency change (v2) ---
        lib_v2 = b'libfoo-v2-content'
        lib_v2_digest = _make_digest(lib_v2)
        dep_artifact_root_v2 = _build_source_tree(cas, {"lib/libfoo.so": lib_v2})
        dep_artifact_v2 = FakeArtifact(FakeSourceDir(dep_artifact_root_v2))
        dep_element_v2 = FakeElement("dep.bst", artifact=dep_artifact_v2)

        # Element sources unchanged
        element_v2 = FakeElement("app.bst", sources=sources)
        artifact_v2 = FakeArtifact(element=element_v2)

        # --- Retrieve ---
        retrieved = artifactcache.get_speculative_actions(artifact_v2, weak_key=weak_key)
        assert retrieved is not None

        # --- Instantiate ---
        element_lookup = {"dep.bst": dep_element_v2}
        instantiator = SpeculativeActionInstantiator(cas, artifactcache)
        result_digest = instantiator.instantiate_action(
            retrieved.actions[0], element_v2, element_lookup
        )

        assert result_digest is not None
        assert result_digest.hash != subaction_digest.hash

        # Verify: main.c unchanged, libfoo.so updated to v2
        new_action = cas.fetch_action(result_digest)
        new_root = cas.fetch_directory_proto(new_action.input_root_digest)

        # Collect all files recursively
        all_files = {}
        self._collect_files(cas, new_root, "", all_files)

        assert all_files["main.c"] == _make_digest(src_content).hash
        assert all_files["lib/libfoo.so"] == lib_v2_digest.hash

    def test_no_change_returns_base_action(self, tmp_path):
        """
        When sources haven't changed between generate and instantiate,
        the instantiator should return the base action digest unchanged.
        """
        cas = FakeCAS()
        artifactcache = FakeArtifactCache(cas, str(tmp_path))

        content = b'unchanged source'
        source_root = _build_source_tree(cas, {"file.c": content})
        sources = FakeSources(FakeSourceDir(source_root))
        element = FakeElement("app.bst", sources=sources)

        subaction_input = _build_source_tree(cas, {"file.c": content})
        subaction_digest = _build_action(cas, subaction_input)

        # Generate and store
        generator = SpeculativeActionsGenerator(cas)
        spec_actions = generator.generate_speculative_actions(element, [subaction_digest], [])

        weak_key = "unchanged-key"
        artifact = FakeArtifact(element=element)
        artifactcache.store_speculative_actions(artifact, spec_actions, weak_key=weak_key)

        # Retrieve and instantiate with same sources
        retrieved = artifactcache.get_speculative_actions(artifact, weak_key=weak_key)
        instantiator = SpeculativeActionInstantiator(cas, artifactcache)
        result_digest = instantiator.instantiate_action(retrieved.actions[0], element, {})

        # Should return the original action digest (no modifications needed)
        assert result_digest.hash == subaction_digest.hash

    def test_multiple_subactions_roundtrip(self, tmp_path):
        """
        Multiple subactions from a single build should each be independently
        instantiatable after a source change.
        """
        cas = FakeCAS()
        artifactcache = FakeArtifactCache(cas, str(tmp_path))

        v1_a = b'void a_v1() {}'
        v1_b = b'void b_v1() {}'

        source_root = _build_source_tree(cas, {"a.c": v1_a, "b.c": v1_b})
        sources = FakeSources(FakeSourceDir(source_root))
        element = FakeElement("app.bst", sources=sources)

        # Two subactions, each using a different source file
        sub1_input = _build_source_tree(cas, {"a.c": v1_a})
        sub1_digest = _build_action(cas, sub1_input)
        sub2_input = _build_source_tree(cas, {"b.c": v1_b})
        sub2_digest = _build_action(cas, sub2_input)

        generator = SpeculativeActionsGenerator(cas)
        spec_actions = generator.generate_speculative_actions(
            element, [sub1_digest, sub2_digest], []
        )
        assert len(spec_actions.actions) == 2

        weak_key = "multi-sub"
        artifact = FakeArtifact(element=element)
        artifactcache.store_speculative_actions(artifact, spec_actions, weak_key=weak_key)

        # Change both source files
        v2_a = b'void a_v2() {}'
        v2_b = b'void b_v2() {}'
        source_root_v2 = _build_source_tree(cas, {"a.c": v2_a, "b.c": v2_b})
        sources_v2 = FakeSources(FakeSourceDir(source_root_v2))
        element_v2 = FakeElement("app.bst", sources=sources_v2)
        artifact_v2 = FakeArtifact(element=element_v2)

        retrieved = artifactcache.get_speculative_actions(artifact_v2, weak_key=weak_key)
        instantiator = SpeculativeActionInstantiator(cas, artifactcache)

        # Both actions should be instantiatable
        for i, spec_action in enumerate(retrieved.actions):
            result = instantiator.instantiate_action(spec_action, element_v2, {})
            assert result is not None
            assert result.hash != [sub1_digest, sub2_digest][i].hash

            new_action = cas.fetch_action(result)
            new_root = cas.fetch_directory_proto(new_action.input_root_digest)
            # Each action should have exactly one file with the v2 digest
            assert len(new_root.files) == 1
            expected_hash = _make_digest([v2_a, v2_b][i]).hash
            assert new_root.files[0].digest.hash == expected_hash

    def test_nested_source_tree_roundtrip(self, tmp_path):
        """
        Source files in nested directories should be correctly tracked
        through generate and instantiate.
        """
        cas = FakeCAS()
        artifactcache = FakeArtifactCache(cas, str(tmp_path))

        v1 = b'nested file v1'
        source_root = _build_source_tree(cas, {"src/lib/util.c": v1})
        sources = FakeSources(FakeSourceDir(source_root))
        element = FakeElement("app.bst", sources=sources)

        # Subaction has the same nested file
        sub_input = _build_source_tree(cas, {"src/lib/util.c": v1})
        sub_digest = _build_action(cas, sub_input)

        generator = SpeculativeActionsGenerator(cas)
        spec_actions = generator.generate_speculative_actions(element, [sub_digest], [])
        assert len(spec_actions.actions) == 1

        weak_key = "nested"
        artifact = FakeArtifact(element=element)
        artifactcache.store_speculative_actions(artifact, spec_actions, weak_key=weak_key)

        # Change the nested file
        v2 = b'nested file v2'
        source_root_v2 = _build_source_tree(cas, {"src/lib/util.c": v2})
        sources_v2 = FakeSources(FakeSourceDir(source_root_v2))
        element_v2 = FakeElement("app.bst", sources=sources_v2)
        artifact_v2 = FakeArtifact(element=element_v2)

        retrieved = artifactcache.get_speculative_actions(artifact_v2, weak_key=weak_key)
        instantiator = SpeculativeActionInstantiator(cas, artifactcache)
        result = instantiator.instantiate_action(retrieved.actions[0], element_v2, {})

        assert result is not None
        assert result.hash != sub_digest.hash

        # Verify nested file was updated
        new_action = cas.fetch_action(result)
        all_files = {}
        self._collect_files(cas, cas.fetch_directory_proto(new_action.input_root_digest), "", all_files)
        assert all_files["src/lib/util.c"] == _make_digest(v2).hash

    def test_weak_key_isolation(self, tmp_path):
        """
        Different weak keys should store and retrieve independent SA sets,
        modeling how different element configurations get separate SA entries.
        """
        cas = FakeCAS()
        artifactcache = FakeArtifactCache(cas, str(tmp_path))

        content_a = b'content for config A'
        content_b = b'content for config B'

        # Store SA under key A
        source_root_a = _build_source_tree(cas, {"file.c": content_a})
        sources_a = FakeSources(FakeSourceDir(source_root_a))
        element_a = FakeElement("app.bst", sources=sources_a)
        sub_a = _build_action(cas, _build_source_tree(cas, {"file.c": content_a}))

        generator = SpeculativeActionsGenerator(cas)
        sa_a = generator.generate_speculative_actions(element_a, [sub_a], [])
        artifact_a = FakeArtifact(element=element_a)
        artifactcache.store_speculative_actions(artifact_a, sa_a, weak_key="key-A")

        # Store SA under key B
        source_root_b = _build_source_tree(cas, {"file.c": content_b})
        sources_b = FakeSources(FakeSourceDir(source_root_b))
        element_b = FakeElement("app.bst", sources=sources_b)
        sub_b = _build_action(cas, _build_source_tree(cas, {"file.c": content_b}))

        sa_b = generator.generate_speculative_actions(element_b, [sub_b], [])
        artifact_b = FakeArtifact(element=element_b)
        artifactcache.store_speculative_actions(artifact_b, sa_b, weak_key="key-B")

        # Retrieve each independently
        ret_a = artifactcache.get_speculative_actions(artifact_a, weak_key="key-A")
        ret_b = artifactcache.get_speculative_actions(artifact_b, weak_key="key-B")

        assert ret_a is not None
        assert ret_b is not None

        # They should reference different base actions
        assert ret_a.actions[0].base_action_digest.hash != ret_b.actions[0].base_action_digest.hash

        # Key A should not return key B's data
        ret_missing = artifactcache.get_speculative_actions(artifact_a, weak_key="key-nonexistent")
        assert ret_missing is None

    def test_priming_scenario(self, tmp_path):
        """
        Models the priming queue's core scenario:

        1. Element app.bst depends on dep.bst
        2. app.bst is built with dep v1 — subactions recorded, SA generated
           and stored under app's weak key
        3. dep.bst is rebuilt with new content (v2)
        4. app.bst needs rebuilding (strict key changed), but its weak key
           is stable (only dep names, not cache keys)
        5. Priming: retrieve SA by weak key, instantiate each action with
           dep v2's artifact digests, verify the adapted actions have the
           correct updated digests

        This is the core value of speculative actions: adapting cached
        build actions to new dependency versions without rebuilding.
        """
        cas = FakeCAS()
        artifactcache = FakeArtifactCache(cas, str(tmp_path))

        # --- Initial build: app depends on dep v1 ---
        app_src = b'#include "dep.h"\nint main() { return dep(); }'
        dep_header_v1 = b'int dep(void); /* v1 */'
        dep_lib_v1 = b'dep-object-code-v1'

        app_source_root = _build_source_tree(cas, {"main.c": app_src})
        app_sources = FakeSources(FakeSourceDir(app_source_root))

        dep_artifact_root_v1 = _build_source_tree(cas, {
            "include/dep.h": dep_header_v1,
            "lib/libdep.o": dep_lib_v1,
        })
        dep_artifact_v1 = FakeArtifact(FakeSourceDir(dep_artifact_root_v1))
        dep_element_v1 = FakeElement("dep.bst", artifact=dep_artifact_v1)

        app_element = FakeElement("app.bst", sources=app_sources)

        # Subactions from app's build: compile (uses main.c + dep.h) and
        # link (uses main.o + libdep.o)
        compile_input = _build_source_tree(cas, {
            "main.c": app_src,
            "include/dep.h": dep_header_v1,
        })
        compile_action = _build_action(cas, compile_input)

        link_input = _build_source_tree(cas, {
            "main.o": b'app-object-code',
            "lib/libdep.o": dep_lib_v1,
        })
        link_action = _build_action(cas, link_input)

        # Generate SA from both subactions
        generator = SpeculativeActionsGenerator(cas)
        spec_actions = generator.generate_speculative_actions(
            app_element, [compile_action, link_action], [dep_element_v1]
        )

        assert len(spec_actions.actions) == 2, (
            f"Expected 2 speculative actions (compile + link), got {len(spec_actions.actions)}"
        )

        # Store under app's weak key
        weak_key = "app-weak-key"
        app_artifact = FakeArtifact(element=app_element)
        artifactcache.store_speculative_actions(
            app_artifact, spec_actions, weak_key=weak_key
        )

        # --- dep.bst rebuilt with v2 ---
        dep_header_v2 = b'int dep(void); /* v2 - added feature */'
        dep_lib_v2 = b'dep-object-code-v2'

        dep_artifact_root_v2 = _build_source_tree(cas, {
            "include/dep.h": dep_header_v2,
            "lib/libdep.o": dep_lib_v2,
        })
        dep_artifact_v2 = FakeArtifact(FakeSourceDir(dep_artifact_root_v2))
        dep_element_v2 = FakeElement("dep.bst", artifact=dep_artifact_v2)

        # app's sources unchanged, weak key stable
        app_element_v2 = FakeElement("app.bst", sources=app_sources)
        app_artifact_v2 = FakeArtifact(element=app_element_v2)

        # --- Priming: retrieve and instantiate ---
        retrieved = artifactcache.get_speculative_actions(
            app_artifact_v2, weak_key=weak_key
        )
        assert retrieved is not None
        assert len(retrieved.actions) == 2

        element_lookup = {"dep.bst": dep_element_v2}
        instantiator = SpeculativeActionInstantiator(cas, artifactcache)

        adapted_actions = []
        for spec_action in retrieved.actions:
            result = instantiator.instantiate_action(
                spec_action, app_element_v2, element_lookup
            )
            assert result is not None
            adapted_actions.append(result)

        # Verify compile action: main.c unchanged, dep.h updated to v2
        compile_result = cas.fetch_action(adapted_actions[0])
        compile_files = {}
        self._collect_files(
            cas,
            cas.fetch_directory_proto(compile_result.input_root_digest),
            "", compile_files,
        )
        assert compile_files["main.c"] == _make_digest(app_src).hash
        assert compile_files["include/dep.h"] == _make_digest(dep_header_v2).hash

        # Verify link action: libdep.o updated to v2
        link_result = cas.fetch_action(adapted_actions[1])
        link_files = {}
        self._collect_files(
            cas,
            cas.fetch_directory_proto(link_result.input_root_digest),
            "", link_files,
        )
        assert link_files["lib/libdep.o"] == _make_digest(dep_lib_v2).hash

    @staticmethod
    def _collect_files(cas, directory, prefix, result):
        """Recursively collect {path: digest_hash} from a Directory proto."""
        if directory is None:
            return
        for f in directory.files:
            path = f.name if not prefix else "{}/{}".format(prefix, f.name)
            result[path] = f.digest.hash
        for d in directory.directories:
            subpath = d.name if not prefix else "{}/{}".format(prefix, d.name)
            subdir = cas.fetch_directory_proto(d.digest)
            TestGenerateStoreRetrieveInstantiate._collect_files(cas, subdir, subpath, result)


# ---------------------------------------------------------------------------
# Fake ActionCache service for ACTION overlay tests
# ---------------------------------------------------------------------------

class FakeACService:
    """Fake ActionCache service that returns stored ActionResults."""

    def __init__(self):
        self._results = {}  # action_digest_hash -> ActionResult proto

    def store_action_result(self, action_digest, action_result):
        self._results[action_digest.hash] = action_result

    def GetActionResult(self, request):
        return self._results.get(request.action_digest.hash)


# ---------------------------------------------------------------------------
# ACTION overlay tests
# ---------------------------------------------------------------------------

class TestActionOverlays:
    """Tests for ACTION overlay generation and instantiation (cross-subaction output chaining)."""

    def test_action_overlay_generated_for_prior_output(self, tmp_path):
        """
        Scenario: compile subaction produces main.o. Link subaction's input
        tree contains main.o. Generator should create an ACTION overlay on
        the link subaction pointing to the compile subaction's output.
        """
        cas = FakeCAS()
        ac_service = FakeACService()

        # --- Build phase ---
        app_src = b'int main() { return 0; }'
        main_o = b'compiled-object-code'
        main_o_digest = _make_digest(main_o)

        # Element sources
        source_root = _build_source_tree(cas, {"main.c": app_src})
        sources = FakeSources(FakeSourceDir(source_root))
        element = FakeElement("app.bst", sources=sources)

        # Compile subaction: input has main.c, output has main.o
        compile_input = _build_source_tree(cas, {"main.c": app_src})
        compile_action_digest = _build_action(cas, compile_input)

        # Store compile's ActionResult with main.o as output
        compile_result = remote_execution_pb2.ActionResult()
        output_file = compile_result.output_files.add()
        output_file.path = "main.o"
        output_file.digest.CopyFrom(main_o_digest)
        ac_service.store_action_result(compile_action_digest, compile_result)

        # Link subaction: input has main.o (output of compile)
        link_input = _build_source_tree(cas, {"main.o": main_o})
        link_action_digest = _build_action(cas, link_input)

        # --- Generate with ac_service ---
        generator = SpeculativeActionsGenerator(cas, ac_service=ac_service)
        spec_actions = generator.generate_speculative_actions(
            element, [compile_action_digest, link_action_digest], []
        )

        # Compile should have SOURCE overlay for main.c
        assert len(spec_actions.actions) >= 2
        compile_sa = spec_actions.actions[0]
        assert any(
            o.type == speculative_actions_pb2.SpeculativeActions.Overlay.SOURCE
            for o in compile_sa.overlays
        )

        # Link should have ACTION overlay for main.o
        link_sa = spec_actions.actions[1]
        action_overlays = [
            o for o in link_sa.overlays
            if o.type == speculative_actions_pb2.SpeculativeActions.Overlay.ACTION
        ]
        assert len(action_overlays) == 1
        ao = action_overlays[0]
        assert ao.source_action_digest.hash == compile_action_digest.hash
        assert ao.source_path == "main.o"
        assert ao.target_digest.hash == main_o_digest.hash

    def test_action_overlay_not_generated_when_covered_by_source(self, tmp_path):
        """
        If a file in the input tree is already resolved as a SOURCE overlay,
        it should NOT get a duplicate ACTION overlay even if it matches a
        prior subaction output.
        """
        cas = FakeCAS()
        ac_service = FakeACService()

        # main.c appears both in sources AND as output of subaction 0
        src_content = b'int main() { return 0; }'
        src_digest = _make_digest(src_content)

        source_root = _build_source_tree(cas, {"main.c": src_content})
        sources = FakeSources(FakeSourceDir(source_root))
        element = FakeElement("app.bst", sources=sources)

        # Subaction 0: some action that happens to output main.c
        sub0_input = _build_source_tree(cas, {"other.c": b'other'})
        sub0_digest = _build_action(cas, sub0_input)
        sub0_result = remote_execution_pb2.ActionResult()
        out = sub0_result.output_files.add()
        out.path = "main.c"
        out.digest.CopyFrom(src_digest)
        ac_service.store_action_result(sub0_digest, sub0_result)

        # Subaction 1: uses main.c
        sub1_input = _build_source_tree(cas, {"main.c": src_content})
        sub1_digest = _build_action(cas, sub1_input)

        generator = SpeculativeActionsGenerator(cas, ac_service=ac_service)
        spec_actions = generator.generate_speculative_actions(
            element, [sub0_digest, sub1_digest], []
        )

        # The second subaction should only have a SOURCE overlay, not ACTION
        sub1_sa = [sa for sa in spec_actions.actions if sa.base_action_digest.hash == sub1_digest.hash]
        assert len(sub1_sa) == 1
        for overlay in sub1_sa[0].overlays:
            assert overlay.type != speculative_actions_pb2.SpeculativeActions.Overlay.ACTION

    def test_action_overlay_instantiation_with_instantiated_actions(self, tmp_path):
        """
        Instantiate an ACTION overlay using instantiated_actions from a prior
        subaction's priming, with the ActionResult in the AC.
        """
        cas = FakeCAS()
        ac_service = FakeACService()
        artifactcache = FakeArtifactCache(cas, str(tmp_path))

        # Build an action whose input tree has main.o
        old_main_o = b'old-object-code'
        old_main_o_digest = _make_digest(old_main_o)
        link_input = _build_source_tree(cas, {"main.o": old_main_o})
        link_action_digest = _build_action(cas, link_input)

        # Create a SpeculativeAction with an ACTION overlay
        # Use a fake compile action digest as the producing action's base
        compile_base_digest = _make_digest(b'fake-compile-action-base')
        # The adapted digest (what was actually executed after priming)
        compile_adapted_digest = _make_digest(b'fake-compile-action-adapted')
        spec_action = speculative_actions_pb2.SpeculativeActions.SpeculativeAction()
        spec_action.base_action_digest.CopyFrom(link_action_digest)
        overlay = spec_action.overlays.add()
        overlay.type = speculative_actions_pb2.SpeculativeActions.Overlay.ACTION
        overlay.source_action_digest.CopyFrom(compile_base_digest)
        overlay.source_path = "main.o"
        overlay.target_digest.CopyFrom(old_main_o_digest)

        # Simulate: compile subaction was instantiated and executed,
        # producing new main.o — result is in AC under adapted digest
        new_main_o = b'new-object-code'
        new_main_o_digest = _make_digest(new_main_o)
        compile_result = remote_execution_pb2.ActionResult()
        out = compile_result.output_files.add()
        out.path = "main.o"
        out.digest.CopyFrom(new_main_o_digest)
        ac_service.store_action_result(compile_adapted_digest, compile_result)

        # Global instantiated_actions: base -> adapted
        instantiated_actions = {compile_base_digest.hash: compile_adapted_digest}

        element = FakeElement("app.bst")
        instantiator = SpeculativeActionInstantiator(cas, artifactcache, ac_service=ac_service)
        result_digest = instantiator.instantiate_action(
            spec_action, element, {},
            instantiated_actions=instantiated_actions,
        )

        assert result_digest is not None
        assert result_digest.hash != link_action_digest.hash

        # Verify the action's input tree has the new main.o digest
        new_action = cas.fetch_action(result_digest)
        new_root = cas.fetch_directory_proto(new_action.input_root_digest)
        assert new_root.files[0].name == "main.o"
        assert new_root.files[0].digest.hash == new_main_o_digest.hash

    def test_action_overlay_full_roundtrip(self, tmp_path):
        """
        Full roundtrip: generate ACTION overlays, store, retrieve,
        instantiate with instantiated_actions from sequential priming execution.

        Models the compile→link scenario where dep.h changes, causing
        main.o to change, which should be chained to the link action.
        """
        cas = FakeCAS()
        ac_service = FakeACService()
        artifactcache = FakeArtifactCache(cas, str(tmp_path))

        # --- Build phase (v1) ---
        app_src = b'#include "dep.h"\nint main() { return dep(); }'
        dep_header_v1 = b'int dep(void); /* v1 */'
        main_o_v1 = b'main-object-v1'
        main_o_v1_digest = _make_digest(main_o_v1)

        source_root = _build_source_tree(cas, {"main.c": app_src})
        sources = FakeSources(FakeSourceDir(source_root))

        dep_artifact_root = _build_source_tree(cas, {"include/dep.h": dep_header_v1})
        dep_artifact = FakeArtifact(FakeSourceDir(dep_artifact_root))
        dep_element_v1 = FakeElement("dep.bst", artifact=dep_artifact)

        element = FakeElement("app.bst", sources=sources)

        # Compile: uses main.c + dep.h, produces main.o
        compile_input = _build_source_tree(cas, {
            "main.c": app_src,
            "include/dep.h": dep_header_v1,
        })
        compile_digest = _build_action(cas, compile_input)

        compile_result = remote_execution_pb2.ActionResult()
        out = compile_result.output_files.add()
        out.path = "main.o"
        out.digest.CopyFrom(main_o_v1_digest)
        ac_service.store_action_result(compile_digest, compile_result)

        # Link: uses main.o
        link_input = _build_source_tree(cas, {"main.o": main_o_v1})
        link_digest = _build_action(cas, link_input)

        # --- Generate ---
        generator = SpeculativeActionsGenerator(cas, ac_service=ac_service)
        spec_actions = generator.generate_speculative_actions(
            element, [compile_digest, link_digest], [dep_element_v1]
        )

        assert len(spec_actions.actions) == 2

        # Verify link has ACTION overlay
        link_sa = spec_actions.actions[1]
        action_overlays = [
            o for o in link_sa.overlays
            if o.type == speculative_actions_pb2.SpeculativeActions.Overlay.ACTION
        ]
        assert len(action_overlays) == 1

        # --- Store ---
        weak_key = "app-weak"
        artifact = FakeArtifact(element=element)
        artifactcache.store_speculative_actions(artifact, spec_actions, weak_key=weak_key)

        # --- dep changes (v2) ---
        dep_header_v2 = b'int dep(void); /* v2 */'
        dep_artifact_root_v2 = _build_source_tree(cas, {"include/dep.h": dep_header_v2})
        dep_artifact_v2 = FakeArtifact(FakeSourceDir(dep_artifact_root_v2))
        dep_element_v2 = FakeElement("dep.bst", artifact=dep_artifact_v2)

        element_v2 = FakeElement("app.bst", sources=sources)
        artifact_v2 = FakeArtifact(element=element_v2)

        # --- Retrieve ---
        retrieved = artifactcache.get_speculative_actions(artifact_v2, weak_key=weak_key)
        assert retrieved is not None

        # --- Sequential instantiation (simulating priming queue) ---
        element_lookup = {"dep.bst": dep_element_v2}
        instantiator = SpeculativeActionInstantiator(cas, artifactcache, ac_service=ac_service)
        instantiated_actions = {}

        # 1) Instantiate compile action (SOURCE + ARTIFACT overlays)
        compile_result_digest = instantiator.instantiate_action(
            retrieved.actions[0], element_v2, element_lookup,
            instantiated_actions=instantiated_actions,
        )
        assert compile_result_digest is not None

        # Record in instantiated_actions (as the priming queue would)
        instantiated_actions[compile_digest.hash] = compile_result_digest

        # Simulate compile execution producing new main.o
        # Store the result in the AC under the adapted digest
        main_o_v2 = b'main-object-v2'
        main_o_v2_digest = _make_digest(main_o_v2)
        compile_v2_result = remote_execution_pb2.ActionResult()
        out = compile_v2_result.output_files.add()
        out.path = "main.o"
        out.digest.CopyFrom(main_o_v2_digest)
        ac_service.store_action_result(compile_result_digest, compile_v2_result)

        # 2) Instantiate link action (ACTION overlay resolves via
        #    instantiated_actions + AC lookup)
        link_result_digest = instantiator.instantiate_action(
            retrieved.actions[1], element_v2, element_lookup,
            instantiated_actions=instantiated_actions,
        )
        assert link_result_digest is not None
        assert link_result_digest.hash != link_digest.hash

        # Verify link action's input tree has new main.o
        link_action = cas.fetch_action(link_result_digest)
        link_root = cas.fetch_directory_proto(link_action.input_root_digest)
        assert link_root.files[0].name == "main.o"
        assert link_root.files[0].digest.hash == main_o_v2_digest.hash

    def test_no_action_overlays_without_ac_service(self, tmp_path):
        """
        When ac_service is None, no ACTION overlays should be generated
        (backward compatibility).
        """
        cas = FakeCAS()

        src_content = b'int main() { return 0; }'
        main_o = b'object-code'

        source_root = _build_source_tree(cas, {"main.c": src_content})
        sources = FakeSources(FakeSourceDir(source_root))
        element = FakeElement("app.bst", sources=sources)

        compile_input = _build_source_tree(cas, {"main.c": src_content})
        compile_digest = _build_action(cas, compile_input)

        link_input = _build_source_tree(cas, {"main.o": main_o})
        link_digest = _build_action(cas, link_input)

        # No ac_service — should behave exactly as before
        generator = SpeculativeActionsGenerator(cas)
        spec_actions = generator.generate_speculative_actions(
            element, [compile_digest, link_digest], []
        )

        # Compile has SOURCE overlay, link has no overlays (main.o unresolved)
        assert len(spec_actions.actions) == 1  # only compile
        for sa in spec_actions.actions:
            for o in sa.overlays:
                assert o.type != speculative_actions_pb2.SpeculativeActions.Overlay.ACTION


class TestCrossElementActionOverlays:
    """Tests for cross-element ACTION overlays (dependency subaction output chaining)."""

    def test_cross_element_action_overlay_generated(self, tmp_path):
        """
        Scenario: dep.bst has a codegen subaction that produces gen.h.
        app.bst's compile subaction uses gen.h in its input tree.
        Generator should create a cross-element ACTION overlay pointing
        to dep.bst's codegen subaction.
        """
        cas = FakeCAS()
        ac_service = FakeACService()
        artifactcache = FakeArtifactCache(cas, str(tmp_path))

        # --- dep.bst was built, generated SAs ---
        gen_h_content = b'/* generated header v1 */'
        gen_h_digest = _make_digest(gen_h_content)

        # dep's codegen subaction produced gen.h
        dep_codegen_input = _build_source_tree(cas, {"schema.xml": b'<schema/>'})
        dep_codegen_digest = _build_action(cas, dep_codegen_input)

        dep_codegen_result = remote_execution_pb2.ActionResult()
        out = dep_codegen_result.output_files.add()
        out.path = "gen.h"
        out.digest.CopyFrom(gen_h_digest)
        ac_service.store_action_result(dep_codegen_digest, dep_codegen_result)

        # dep's artifact contains gen.h (installed)
        dep_artifact_root = _build_source_tree(cas, {"include/gen.h": gen_h_content})
        dep_artifact = FakeArtifact(FakeSourceDir(dep_artifact_root))
        dep_element = FakeElement("dep.bst", artifact=dep_artifact)

        # dep's stored SpeculativeActions
        dep_sa = speculative_actions_pb2.SpeculativeActions()
        dep_spec_action = dep_sa.actions.add()
        dep_spec_action.base_action_digest.CopyFrom(dep_codegen_digest)
        dep_sa_artifact = FakeArtifact(element=dep_element)
        artifactcache.store_speculative_actions(dep_sa_artifact, dep_sa, weak_key="dep-weak")

        # Patch dep_artifact to return the stored SA
        dep_artifact._sa = dep_sa
        original_get_sa = artifactcache.get_speculative_actions
        def get_sa_with_dep(artifact, weak_key=None):
            if hasattr(artifact, '_sa'):
                return artifact._sa
            return original_get_sa(artifact, weak_key=weak_key)
        artifactcache.get_speculative_actions = get_sa_with_dep

        # --- app.bst build: compile uses gen.h from dep ---
        app_src = b'#include "gen.h"\nint main() {}'
        app_source_root = _build_source_tree(cas, {"main.c": app_src})
        app_sources = FakeSources(FakeSourceDir(app_source_root))
        app_element = FakeElement("app.bst", sources=app_sources)

        # app's compile subaction input has main.c and gen.h
        compile_input = _build_source_tree(cas, {
            "main.c": app_src,
            "include/gen.h": gen_h_content,
        })
        compile_digest = _build_action(cas, compile_input)

        # --- Generate SAs for app ---
        generator = SpeculativeActionsGenerator(
            cas, ac_service=ac_service, artifactcache=artifactcache
        )
        spec_actions = generator.generate_speculative_actions(
            app_element, [compile_digest], [dep_element]
        )

        assert len(spec_actions.actions) == 1
        overlays = spec_actions.actions[0].overlays

        # main.c should be SOURCE overlay
        source_overlays = [
            o for o in overlays
            if o.type == speculative_actions_pb2.SpeculativeActions.Overlay.SOURCE
        ]
        assert len(source_overlays) == 1
        assert source_overlays[0].source_path == "main.c"

        # gen.h could be ARTIFACT (from dep's artifact tree) or ACTION
        # (from dep's codegen subaction output).  ARTIFACT takes priority
        # in the digest cache, but gen.h in the input tree at include/gen.h
        # has the same content digest as dep's codegen output.
        # Since SOURCE/ARTIFACT are checked first, gen.h at include/gen.h
        # should be an ARTIFACT overlay (dep's artifact has it).
        # But the gen.h digest also matches dep's codegen output — since
        # ARTIFACT already covers it, no ACTION overlay should be created.
        action_overlays = [
            o for o in overlays
            if o.type == speculative_actions_pb2.SpeculativeActions.Overlay.ACTION
        ]
        artifact_overlays = [
            o for o in overlays
            if o.type == speculative_actions_pb2.SpeculativeActions.Overlay.ARTIFACT
        ]
        assert len(artifact_overlays) == 1
        assert artifact_overlays[0].source_path == "include/gen.h"
        assert len(action_overlays) == 0  # Covered by ARTIFACT

    def test_cross_element_action_overlay_for_intermediate_file(self, tmp_path):
        """
        When a dependency subaction produces an intermediate file that is
        NOT in the dependency's artifact but IS in the current element's
        subaction input tree, a cross-element ACTION overlay should be
        generated (since ARTIFACT can't cover it).
        """
        cas = FakeCAS()
        ac_service = FakeACService()
        artifactcache = FakeArtifactCache(cas, str(tmp_path))

        # dep.bst: codegen produces intermediate.h but only installs final.h
        intermediate_content = b'/* intermediate */'
        intermediate_digest = _make_digest(intermediate_content)

        dep_codegen_input = _build_source_tree(cas, {"schema.xml": b'<schema/>'})
        dep_codegen_digest = _build_action(cas, dep_codegen_input)

        dep_result = remote_execution_pb2.ActionResult()
        out = dep_result.output_files.add()
        out.path = "intermediate.h"
        out.digest.CopyFrom(intermediate_digest)
        ac_service.store_action_result(dep_codegen_digest, dep_result)

        # dep's artifact only has final.h (intermediate.h not installed)
        dep_artifact_root = _build_source_tree(cas, {"include/final.h": b'/* final */'})
        dep_artifact = FakeArtifact(FakeSourceDir(dep_artifact_root))
        dep_element = FakeElement("dep.bst", artifact=dep_artifact)

        # dep's stored SA
        dep_sa = speculative_actions_pb2.SpeculativeActions()
        dep_spec = dep_sa.actions.add()
        dep_spec.base_action_digest.CopyFrom(dep_codegen_digest)
        dep_artifact._sa = dep_sa
        def get_sa(artifact, weak_key=None):
            if hasattr(artifact, '_sa'):
                return artifact._sa
            return None
        artifactcache.get_speculative_actions = get_sa

        # app.bst compile uses intermediate.h (somehow available in sandbox)
        app_src = b'#include "intermediate.h"'
        app_source_root = _build_source_tree(cas, {"main.c": app_src})
        app_sources = FakeSources(FakeSourceDir(app_source_root))
        app_element = FakeElement("app.bst", sources=app_sources)

        compile_input = _build_source_tree(cas, {
            "main.c": app_src,
            "intermediate.h": intermediate_content,
        })
        compile_digest = _build_action(cas, compile_input)

        # Generate
        generator = SpeculativeActionsGenerator(
            cas, ac_service=ac_service, artifactcache=artifactcache
        )
        spec_actions = generator.generate_speculative_actions(
            app_element, [compile_digest], [dep_element]
        )

        assert len(spec_actions.actions) == 1
        overlays = spec_actions.actions[0].overlays

        # intermediate.h is not in sources or dep artifact → ACTION overlay
        action_overlays = [
            o for o in overlays
            if o.type == speculative_actions_pb2.SpeculativeActions.Overlay.ACTION
        ]
        assert len(action_overlays) == 1
        ao = action_overlays[0]
        assert ao.source_element == "dep.bst"
        assert ao.source_action_digest.hash == dep_codegen_digest.hash
        assert ao.source_path == "intermediate.h"
        assert ao.target_digest.hash == intermediate_digest.hash

    def test_cross_element_action_overlay_instantiation(self, tmp_path):
        """
        Instantiate a cross-element ACTION overlay by looking up the
        producing subaction's ActionResult from the action cache.
        """
        cas = FakeCAS()
        ac_service = FakeACService()
        artifactcache = FakeArtifactCache(cas, str(tmp_path))

        # Old intermediate file in the action's input tree
        old_content = b'/* old intermediate */'
        old_digest = _make_digest(old_content)
        action_input = _build_source_tree(cas, {"intermediate.h": old_content})
        action_digest = _build_action(cas, action_input)

        # The producing subaction's new ActionResult (dep was rebuilt)
        dep_codegen_digest = _make_digest(b'dep-codegen-action')
        new_content = b'/* new intermediate */'
        new_digest = _make_digest(new_content)
        new_result = remote_execution_pb2.ActionResult()
        out = new_result.output_files.add()
        out.path = "intermediate.h"
        out.digest.CopyFrom(new_digest)
        ac_service.store_action_result(dep_codegen_digest, new_result)

        # Build a SpeculativeAction with cross-element ACTION overlay
        spec_action = speculative_actions_pb2.SpeculativeActions.SpeculativeAction()
        spec_action.base_action_digest.CopyFrom(action_digest)
        overlay = spec_action.overlays.add()
        overlay.type = speculative_actions_pb2.SpeculativeActions.Overlay.ACTION
        overlay.source_element = "dep.bst"
        overlay.source_action_digest.CopyFrom(dep_codegen_digest)
        overlay.source_path = "intermediate.h"
        overlay.target_digest.CopyFrom(old_digest)

        element = FakeElement("app.bst")
        instantiator = SpeculativeActionInstantiator(
            cas, artifactcache, ac_service=ac_service
        )
        # Cross-element: the dep's codegen action was instantiated and
        # its result is in AC.  instantiated_actions maps base -> adapted
        # (in this case, same digest since we stored under dep_codegen_digest).
        instantiated_actions = {dep_codegen_digest.hash: dep_codegen_digest}
        result_digest = instantiator.instantiate_action(
            spec_action, element, {},
            instantiated_actions=instantiated_actions,
        )

        assert result_digest is not None
        assert result_digest.hash != action_digest.hash

        new_action = cas.fetch_action(result_digest)
        new_root = cas.fetch_directory_proto(new_action.input_root_digest)
        assert new_root.files[0].name == "intermediate.h"
        assert new_root.files[0].digest.hash == new_digest.hash


# ---------------------------------------------------------------------------
# Speculative action mode tests
# ---------------------------------------------------------------------------

class TestSpeculativeActionModes:
    """Tests verifying that each mode generates the correct overlay types."""

    def _build_compile_link_scenario(self, cas, ac_service):
        """Build a compile→link scenario with source, artifact, and action overlays.

        Returns (element, dep_element, subaction_digests, dependencies)
        """
        app_src = b'int main() { return dep(); }'
        dep_header = b'int dep(void);'
        main_o = b'main-object-code'
        main_o_digest = _make_digest(main_o)

        source_root = _build_source_tree(cas, {"main.c": app_src})
        sources = FakeSources(FakeSourceDir(source_root))

        dep_artifact_root = _build_source_tree(cas, {"include/dep.h": dep_header})
        dep_artifact = FakeArtifact(FakeSourceDir(dep_artifact_root))
        dep_element = FakeElement("dep.bst", artifact=dep_artifact)

        element = FakeElement("app.bst", sources=sources)

        # Compile: uses main.c + dep.h, produces main.o
        compile_input = _build_source_tree(cas, {
            "main.c": app_src,
            "include/dep.h": dep_header,
        })
        compile_digest = _build_action(cas, compile_input)

        compile_result = remote_execution_pb2.ActionResult()
        out = compile_result.output_files.add()
        out.path = "main.o"
        out.digest.CopyFrom(main_o_digest)
        ac_service.store_action_result(compile_digest, compile_result)

        # Link: uses main.o (output of compile)
        link_input = _build_source_tree(cas, {"main.o": main_o})
        link_digest = _build_action(cas, link_input)

        return element, dep_element, [compile_digest, link_digest], [dep_element]

    def test_source_artifact_mode_no_action_overlays(self, tmp_path):
        """source-artifact mode should produce only SOURCE and ARTIFACT overlays."""
        from buildstream.types import _SpeculativeActionMode

        cas = FakeCAS()
        ac_service = FakeACService()

        element, dep_element, subaction_digests, dependencies = \
            self._build_compile_link_scenario(cas, ac_service)

        generator = SpeculativeActionsGenerator(cas, ac_service=ac_service)
        spec_actions = generator.generate_speculative_actions(
            element, subaction_digests, dependencies,
            mode=_SpeculativeActionMode.SOURCE_ARTIFACT,
        )

        # Should have spec_actions for subactions with SOURCE/ARTIFACT overlays
        assert len(spec_actions.actions) >= 1

        # No ACTION overlays should exist in any spec_action
        for sa in spec_actions.actions:
            for overlay in sa.overlays:
                assert overlay.type != speculative_actions_pb2.SpeculativeActions.Overlay.ACTION, \
                    "source-artifact mode should not produce ACTION overlays"

    def test_intra_element_mode_has_action_overlays(self, tmp_path):
        """intra-element mode should produce ACTION overlays for within-element chains."""
        from buildstream.types import _SpeculativeActionMode

        cas = FakeCAS()
        ac_service = FakeACService()

        element, dep_element, subaction_digests, dependencies = \
            self._build_compile_link_scenario(cas, ac_service)

        generator = SpeculativeActionsGenerator(cas, ac_service=ac_service)
        spec_actions = generator.generate_speculative_actions(
            element, subaction_digests, dependencies,
            mode=_SpeculativeActionMode.INTRA_ELEMENT,
        )

        # Should have 2 spec_actions (compile + link)
        assert len(spec_actions.actions) == 2

        # The link action should have an ACTION overlay for main.o
        link_sa = spec_actions.actions[1]
        action_overlays = [
            o for o in link_sa.overlays
            if o.type == speculative_actions_pb2.SpeculativeActions.Overlay.ACTION
        ]
        assert len(action_overlays) == 1
        assert action_overlays[0].source_path == "main.o"

        # ACTION overlays should be intra-element only (source_element empty)
        for sa in spec_actions.actions:
            for overlay in sa.overlays:
                if overlay.type == speculative_actions_pb2.SpeculativeActions.Overlay.ACTION:
                    assert overlay.source_element == "", \
                        "intra-element mode should not produce cross-element ACTION overlays"

    def test_full_mode_has_cross_element_action_overlays(self, tmp_path):
        """full mode should produce cross-element ACTION overlays from dep subactions."""
        from buildstream.types import _SpeculativeActionMode

        cas = FakeCAS()
        ac_service = FakeACService()
        artifactcache = FakeArtifactCache(cas, str(tmp_path))

        # dep element has a subaction that produces intermediate.h
        dep_intermediate = b'/* generated header */'
        dep_intermediate_digest = _make_digest(dep_intermediate)

        dep_compile_input = _build_source_tree(cas, {"gen.c": b'void gen() {}'})
        dep_compile_digest = _build_action(cas, dep_compile_input)

        dep_result = remote_execution_pb2.ActionResult()
        out = dep_result.output_files.add()
        out.path = "intermediate.h"
        out.digest.CopyFrom(dep_intermediate_digest)
        ac_service.store_action_result(dep_compile_digest, dep_result)

        # Create dep artifact and store dep SA on it
        dep_element_obj = FakeElement("dep.bst")
        dep_artifact = FakeArtifact(element=dep_element_obj)

        dep_sa = speculative_actions_pb2.SpeculativeActions()
        dep_spec = dep_sa.actions.add()
        dep_spec.base_action_digest.CopyFrom(dep_compile_digest)
        artifactcache.store_speculative_actions(dep_artifact, dep_sa)

        # Current element uses intermediate.h in its compile input
        source_root = _build_source_tree(cas, {"main.c": b'#include "intermediate.h"'})
        sources = FakeSources(FakeSourceDir(source_root))
        element = FakeElement("app.bst", sources=sources)

        compile_input = _build_source_tree(cas, {
            "main.c": b'#include "intermediate.h"',
            "intermediate.h": dep_intermediate,
        })
        compile_digest = _build_action(cas, compile_input)

        # dep_element must use the SAME artifact object so
        # get_speculative_actions finds the stored SA
        dep_element_obj._artifact = dep_artifact
        dep_element = dep_element_obj

        generator = SpeculativeActionsGenerator(
            cas, ac_service=ac_service, artifactcache=artifactcache
        )
        spec_actions = generator.generate_speculative_actions(
            element, [compile_digest], [dep_element],
            mode=_SpeculativeActionMode.FULL,
        )

        assert len(spec_actions.actions) == 1

        # Should have a cross-element ACTION overlay for intermediate.h
        action_overlays = [
            o for o in spec_actions.actions[0].overlays
            if o.type == speculative_actions_pb2.SpeculativeActions.Overlay.ACTION
        ]
        assert len(action_overlays) == 1
        assert action_overlays[0].source_element == "dep.bst"
        assert action_overlays[0].source_path == "intermediate.h"

    def test_mode_backward_compat_bool(self):
        """Boolean True/False should map to full/none modes."""
        from buildstream.types import _SpeculativeActionMode

        # Verify enum values exist and are distinct
        assert _SpeculativeActionMode.NONE.value == "none"
        assert _SpeculativeActionMode.PRIME_ONLY.value == "prime-only"
        assert _SpeculativeActionMode.SOURCE_ARTIFACT.value == "source-artifact"
        assert _SpeculativeActionMode.INTRA_ELEMENT.value == "intra-element"
        assert _SpeculativeActionMode.FULL.value == "full"

    def test_source_artifact_mode_fewer_ac_calls(self, tmp_path):
        """source-artifact mode should make zero AC calls during generation."""
        from buildstream.types import _SpeculativeActionMode

        cas = FakeCAS()

        # Use a counting AC service to verify zero calls
        class CountingACService:
            def __init__(self):
                self.call_count = 0
                self._results = {}
            def store_action_result(self, action_digest, action_result):
                self._results[action_digest.hash] = action_result
            def GetActionResult(self, request):
                self.call_count += 1
                return self._results.get(request.action_digest.hash)

        ac_service = CountingACService()

        element, dep_element, subaction_digests, dependencies = \
            self._build_compile_link_scenario(cas, ac_service)

        # source-artifact mode: generator should NOT use ac_service
        generator = SpeculativeActionsGenerator(cas, ac_service=ac_service)
        spec_actions = generator.generate_speculative_actions(
            element, subaction_digests, dependencies,
            mode=_SpeculativeActionMode.SOURCE_ARTIFACT,
        )

        assert ac_service.call_count == 0, \
            f"source-artifact mode should make 0 AC calls, got {ac_service.call_count}"

    def test_intra_element_mode_limited_ac_calls(self, tmp_path):
        """intra-element mode should only make AC calls for own subactions."""
        from buildstream.types import _SpeculativeActionMode

        cas = FakeCAS()

        class CountingACService:
            def __init__(self):
                self.call_count = 0
                self._results = {}
            def store_action_result(self, action_digest, action_result):
                self._results[action_digest.hash] = action_result
            def GetActionResult(self, request):
                self.call_count += 1
                return self._results.get(request.action_digest.hash)

        ac_service = CountingACService()

        element, dep_element, subaction_digests, dependencies = \
            self._build_compile_link_scenario(cas, ac_service)

        # intra-element mode: should call AC for own subactions only
        # (2 subactions = 2 _record_subaction_outputs calls)
        generator = SpeculativeActionsGenerator(cas, ac_service=ac_service)
        spec_actions = generator.generate_speculative_actions(
            element, subaction_digests, dependencies,
            mode=_SpeculativeActionMode.INTRA_ELEMENT,
        )

        # Should be exactly N calls for N subactions (no dep seeding)
        assert ac_service.call_count == len(subaction_digests), \
            f"intra-element mode should make {len(subaction_digests)} AC calls " \
            f"(one per own subaction), got {ac_service.call_count}"
