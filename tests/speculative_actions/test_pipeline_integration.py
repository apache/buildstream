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

    def store_speculative_actions(self, artifact, spec_actions, weak_key=None):
        # Store proto in CAS
        spec_actions_digest = self.cas.store_proto(spec_actions)

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
        if weak_key:
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
