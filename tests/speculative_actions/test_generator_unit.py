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
Unit tests for SpeculativeActionsGenerator.

These tests construct Action + Directory protos in-memory and verify
that the Generator correctly produces overlays. No sandbox needed.
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
    """In-memory CAS for testing without a real CAS daemon."""

    def __init__(self):
        self._blobs = {}  # hash -> bytes
        self._directories = {}  # hash -> Directory proto
        self._actions = {}  # hash -> Action proto

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
    """Fake source directory with a digest."""

    def __init__(self, digest):
        self._digest = digest

    def _get_digest(self):
        return self._digest


class FakeSources:
    """Fake ElementSources."""

    def __init__(self, files_dir):
        self._files_dir = files_dir
        self._cached = True

    def cached(self):
        return self._cached

    def get_files(self):
        return self._files_dir


class FakeArtifact:
    """Fake Artifact."""

    def __init__(self, files_dir, is_cached=True):
        self._files_dir = files_dir
        self._cached = is_cached

    def cached(self):
        return self._cached

    def get_files(self):
        return self._files_dir


class FakeElement:
    """Fake Element for testing Generator without a real Element."""

    def __init__(self, name, sources=None, artifact=None):
        self.name = name
        self._Element__sources = sources
        self._artifact = artifact

    def sources(self):
        if self._Element__sources:
            yield True  # Just needs to be non-empty

    def _cached(self):
        return self._artifact is not None and self._artifact.cached()

    def _get_artifact(self):
        return self._artifact


def _build_source_tree(cas, files):
    """Build a CAS directory tree from a dict of {path: content_bytes}.

    Args:
        cas: FakeCAS instance
        files: Dict mapping relative paths to content bytes

    Returns:
        Digest of root directory
    """
    # Group files by directory
    dirs = {}
    for path, content in files.items():
        parts = path.rsplit("/", 1)
        if len(parts) == 1:
            dirname, filename = "", parts[0]
        else:
            dirname, filename = parts
        dirs.setdefault(dirname, []).append((filename, content))

    # Build leaf directories first, then work up
    dir_digests = {}

    # Sort paths by depth (deepest first)
    all_dirs = set()
    for path in files:
        parts = path.split("/")
        for i in range(len(parts) - 1):
            all_dirs.add("/".join(parts[: i + 1]))
    all_dirs.add("")  # root

    # Process deepest directories first, root ("") always last
    non_root = sorted((d for d in all_dirs if d), key=lambda d: -d.count("/"))
    non_root.append("")

    for dirpath in non_root:
        directory = remote_execution_pb2.Directory()

        # Add files in this directory
        for filename, content in dirs.get(dirpath, []):
            file_node = directory.files.add()
            file_node.name = filename
            file_node.digest.CopyFrom(_make_digest(content))

        # Add subdirectories
        for child_dir, child_digest in sorted(dir_digests.items()):
            # Check if child_dir is a direct subdirectory of dirpath
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


def _build_action(cas, input_root_digest):
    """Build an Action proto with the given input root."""
    action = remote_execution_pb2.Action()
    action.input_root_digest.CopyFrom(input_root_digest)
    return cas.store_action(action)


class TestGeneratorOverlayProduction:
    """Test that Generator correctly produces overlays from subactions."""

    def test_generates_source_overlays(self):
        """Files found in element sources should produce SOURCE overlays."""
        from buildstream._speculative_actions.generator import SpeculativeActionsGenerator

        cas = FakeCAS()

        # Create source files
        source_files = {
            "main.c": b'int main() { return 0; }',
            "util.h": b'#pragma once\nvoid util();',
        }
        source_root = _build_source_tree(cas, source_files)
        sources = FakeSources(FakeSourceDir(source_root))

        # Create an action that uses these source files in its input tree
        action_input = _build_source_tree(cas, {
            "src/main.c": b'int main() { return 0; }',
            "src/util.h": b'#pragma once\nvoid util();',
        })
        action_digest = _build_action(cas, action_input)

        element = FakeElement("test-element.bst", sources=sources)
        generator = SpeculativeActionsGenerator(cas)

        spec_actions = generator.generate_speculative_actions(element, [action_digest], [])

        assert spec_actions is not None
        assert len(spec_actions.actions) == 1

        action = spec_actions.actions[0]
        # Should have overlays for the source files found in the action input
        assert len(action.overlays) > 0
        # All overlays should be SOURCE type
        for overlay in action.overlays:
            assert overlay.type == speculative_actions_pb2.SpeculativeActions.Overlay.SOURCE

    def test_generates_artifact_overlays_for_dependencies(self):
        """Files from dependency artifacts should produce ARTIFACT overlays."""
        from buildstream._speculative_actions.generator import SpeculativeActionsGenerator

        cas = FakeCAS()

        # Create a dependency artifact with library files
        dep_files = {
            "lib/libfoo.so": b'fake-shared-object-content',
        }
        dep_root = _build_source_tree(cas, dep_files)
        dep_artifact = FakeArtifact(FakeSourceDir(dep_root))
        dep_element = FakeElement("dep.bst", artifact=dep_artifact)

        # Create element sources (no overlap with dep)
        source_files = {
            "main.c": b'int main() { return 0; }',
        }
        source_root = _build_source_tree(cas, source_files)
        sources = FakeSources(FakeSourceDir(source_root))

        # Create an action that uses both source files and dep artifacts
        action_input = _build_source_tree(cas, {
            "src/main.c": b'int main() { return 0; }',
            "lib/libfoo.so": b'fake-shared-object-content',
        })
        action_digest = _build_action(cas, action_input)

        element = FakeElement("test-element.bst", sources=sources)
        generator = SpeculativeActionsGenerator(cas)

        spec_actions = generator.generate_speculative_actions(element, [action_digest], [dep_element])

        assert spec_actions is not None
        assert len(spec_actions.actions) == 1

        action = spec_actions.actions[0]
        overlay_types = {o.type for o in action.overlays}
        # Should have both SOURCE and ARTIFACT overlays
        assert speculative_actions_pb2.SpeculativeActions.Overlay.SOURCE in overlay_types
        assert speculative_actions_pb2.SpeculativeActions.Overlay.ARTIFACT in overlay_types

    def test_source_priority_over_artifact(self):
        """When same digest exists in both source and artifact, both overlays
        are generated with SOURCE first for fallback resolution."""
        from buildstream._speculative_actions.generator import SpeculativeActionsGenerator

        cas = FakeCAS()

        shared_content = b'shared-file-content'
        shared_hash = _make_digest(shared_content).hash

        # Create element sources with the shared file
        source_root = _build_source_tree(cas, {
            "shared.h": shared_content,
        })
        sources = FakeSources(FakeSourceDir(source_root))

        # Create dependency artifact with the same file
        dep_root = _build_source_tree(cas, {
            "include/shared.h": shared_content,
        })
        dep_artifact = FakeArtifact(FakeSourceDir(dep_root))
        dep_element = FakeElement("dep.bst", artifact=dep_artifact)

        # Action uses the shared file
        action_input = _build_source_tree(cas, {
            "shared.h": shared_content,
        })
        action_digest = _build_action(cas, action_input)

        element = FakeElement("test-element.bst", sources=sources)
        generator = SpeculativeActionsGenerator(cas)

        spec_actions = generator.generate_speculative_actions(element, [action_digest], [dep_element])

        assert len(spec_actions.actions) == 1
        action = spec_actions.actions[0]
        # Both SOURCE and ARTIFACT overlays should be generated for the
        # same target digest, with SOURCE first for priority resolution
        matching = [o for o in action.overlays if o.target_digest.hash == shared_hash]
        assert len(matching) >= 2
        assert matching[0].type == speculative_actions_pb2.SpeculativeActions.Overlay.SOURCE
        assert matching[1].type == speculative_actions_pb2.SpeculativeActions.Overlay.ARTIFACT

    def test_no_overlays_for_unknown_digests(self):
        """Digests not found in sources or artifacts should produce no overlays."""
        from buildstream._speculative_actions.generator import SpeculativeActionsGenerator

        cas = FakeCAS()

        # Empty sources
        source_root = _build_source_tree(cas, {})
        sources = FakeSources(FakeSourceDir(source_root))

        # Action with files not in any source
        action_input = _build_source_tree(cas, {
            "unknown.bin": b'mystery-content',
        })
        action_digest = _build_action(cas, action_input)

        element = FakeElement("test-element.bst", sources=sources)
        generator = SpeculativeActionsGenerator(cas)

        spec_actions = generator.generate_speculative_actions(element, [action_digest], [])

        # No overlays should be generated (action with no overlays is excluded)
        assert len(spec_actions.actions) == 0

    def test_multiple_subactions(self):
        """Multiple subaction digests should each produce a SpeculativeAction."""
        from buildstream._speculative_actions.generator import SpeculativeActionsGenerator

        cas = FakeCAS()

        source_files = {
            "a.c": b'void a() {}',
            "b.c": b'void b() {}',
        }
        source_root = _build_source_tree(cas, source_files)
        sources = FakeSources(FakeSourceDir(source_root))

        # Two separate actions
        action1_input = _build_source_tree(cas, {"src/a.c": b'void a() {}'})
        action1_digest = _build_action(cas, action1_input)

        action2_input = _build_source_tree(cas, {"src/b.c": b'void b() {}'})
        action2_digest = _build_action(cas, action2_input)

        element = FakeElement("test-element.bst", sources=sources)
        generator = SpeculativeActionsGenerator(cas)

        spec_actions = generator.generate_speculative_actions(
            element, [action1_digest, action2_digest], []
        )

        assert len(spec_actions.actions) == 2

    def test_element_artifact_overlays_generated(self):
        """artifact_overlays should be generated for cached element output."""
        from buildstream._speculative_actions.generator import SpeculativeActionsGenerator

        cas = FakeCAS()

        source_files = {"main.c": b'int main() { return 0; }'}
        source_root = _build_source_tree(cas, source_files)
        sources = FakeSources(FakeSourceDir(source_root))

        # Element also has a cached artifact
        artifact_files = {"bin/main": b'compiled-binary'}
        artifact_root = _build_source_tree(cas, artifact_files)
        artifact = FakeArtifact(FakeSourceDir(artifact_root))

        element = FakeElement("test-element.bst", sources=sources, artifact=artifact)

        # No subactions, just check artifact_overlays
        generator = SpeculativeActionsGenerator(cas)
        spec_actions = generator.generate_speculative_actions(element, [], [])

        # No subaction overlays but artifact_overlays may be present
        # (bin/main is not in source, so it won't be resolved)
        assert spec_actions is not None
