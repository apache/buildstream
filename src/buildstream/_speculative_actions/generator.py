#
#  Copyright 2025 The Apache Software Foundation
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
SpeculativeActionsGenerator
============================

Generates SpeculativeActions and artifact overlays after element builds.

This module is responsible for:
1. Extracting subaction digests from ActionResult
2. Traversing action input trees to find all file digests
3. Resolving digests to their source elements (SOURCE > ARTIFACT priority)
4. Creating overlays for each digest
5. Generating artifact_overlays for the element's output files
"""

from typing import Dict, Tuple


class SpeculativeActionsGenerator:
    """
    Generates SpeculativeActions from element builds.

    This class analyzes completed element builds to extract subactions and
    generate overlay metadata that describes how to adapt inputs for future
    builds.
    """

    def __init__(self, cas):
        """
        Initialize the generator.

        Args:
            cas: The CAS cache for fetching actions and directories
        """
        self._cas = cas
        # Cache for digest.hash -> (element, path, type) lookups
        self._digest_cache: Dict[str, Tuple[str, str, str]] = {}

    def generate_speculative_actions(self, element, subaction_digests, dependencies):
        """
        Generate SpeculativeActions for an element build.

        This is the main entry point for overlay generation. It processes
        all subactions from the element's build and generates overlays
        for each.

        Args:
            element: The element that was built
            subaction_digests: List of Action digests from the build (from ActionResult.subactions)
            dependencies: List of dependency elements (for resolving artifact overlays)

        Returns:
            A SpeculativeActions message containing:
            - actions: SpeculativeActions with overlays for each subaction
            - artifact_overlays: Overlays mapping artifact file digests to sources
        """
        from .._protos.buildstream.v2 import speculative_actions_pb2

        spec_actions = speculative_actions_pb2.SpeculativeActions()

        # Build digest lookup tables from element sources and dependencies
        self._build_digest_cache(element, dependencies)

        # Generate overlays for each subaction
        for subaction_digest in subaction_digests:
            spec_action = self._generate_action_overlays(element, subaction_digest)
            if spec_action:
                spec_actions.actions.append(spec_action)

        # Generate artifact overlays for the element's output files
        artifact_overlays = self._generate_artifact_overlays(element)
        spec_actions.artifact_overlays.extend(artifact_overlays)

        return spec_actions

    def _build_digest_cache(self, element, dependencies):
        """
        Build a cache mapping file digests to their source elements.

        Args:
            element: The element being processed
            dependencies: List of dependency elements
        """
        self._digest_cache.clear()

        # Index element's own sources (highest priority)
        self._index_element_sources(element, element)

        # Index dependency artifacts (lower priority)
        for dep in dependencies:
            self._index_element_artifact(dep)

    def _index_element_sources(self, element, source_element):
        """
        Index all file digests in an element's source tree.

        Args:
            element: The element whose sources to index
            source_element: The element to record as the source
        """
        # Get the element's source directory
        try:
            # Check if element has any sources
            if not any(element.sources()):
                return

            # Access the private __sources attribute to get ElementSources
            sources = element._Element__sources
            if not sources or not sources.cached():
                return

            source_dir = sources.get_files()
            if not source_dir:
                return

            # Traverse the source directory and index all files with full paths
            self._traverse_directory_with_paths(
                source_dir._get_digest(), source_element.name, "SOURCE", ""  # Start with empty path
            )
        except Exception as e:
            # Gracefully handle missing sources
            pass

    def _index_element_artifact(self, element):
        """
        Index all file digests in an element's artifact output.

        Args:
            element: The element whose artifact to index
        """
        try:
            # Check if element is cached
            if not element._cached():
                return

            # Get the artifact object
            artifact = element._get_artifact()
            if not artifact or not artifact.cached():
                return

            # Get the artifact files directory
            files_dir = artifact.get_files()
            if not files_dir:
                return

            # Traverse the artifact files directory with full paths
            self._traverse_directory_with_paths(
                files_dir._get_digest(), element.name, "ARTIFACT", ""  # Start with empty path
            )
        except Exception as e:
            # Gracefully handle missing artifacts
            pass

    def _traverse_directory_with_paths(self, directory_digest, element_name, overlay_type, current_path):
        """
        Recursively traverse a Directory tree and index all file digests with full paths.

        Args:
            directory_digest: The Directory digest to traverse
            element_name: The element name to associate with found files
            overlay_type: Either "SOURCE" or "ARTIFACT"
            current_path: Current relative path from root (e.g., "src/foo")
        """
        try:
            directory = self._cas.fetch_directory_proto(directory_digest)
            if not directory:
                return

            # Index all files in this directory with full paths
            for file_node in directory.files:
                digest_hash = file_node.digest.hash
                # Build full relative path
                file_path = file_node.name if not current_path else f"{current_path}/{file_node.name}"

                # Priority: SOURCE > ARTIFACT
                # Only store if not already present, or if upgrading from ARTIFACT to SOURCE
                if digest_hash not in self._digest_cache:
                    self._digest_cache[digest_hash] = (element_name, file_path, overlay_type)
                elif overlay_type == "SOURCE" and self._digest_cache[digest_hash][2] == "ARTIFACT":
                    # Upgrade ARTIFACT to SOURCE
                    self._digest_cache[digest_hash] = (element_name, file_path, overlay_type)

            # Recursively traverse subdirectories
            for dir_node in directory.directories:
                # Build path for subdirectory
                subdir_path = dir_node.name if not current_path else f"{current_path}/{dir_node.name}"
                self._traverse_directory_with_paths(dir_node.digest, element_name, overlay_type, subdir_path)
        except Exception as e:
            # Gracefully handle errors
            pass

    def _generate_action_overlays(self, element, action_digest):
        """
        Generate overlays for a single subaction.

        Args:
            element: The element being processed
            action_digest: The Action digest to generate overlays for

        Returns:
            SpeculativeAction proto or None if action not found
        """
        from .._protos.buildstream.v2 import speculative_actions_pb2

        # Fetch the action from CAS
        action = self._cas.fetch_action(action_digest)
        if not action:
            return None

        spec_action = speculative_actions_pb2.SpeculativeActions.SpeculativeAction()
        spec_action.base_action_digest.CopyFrom(action_digest)

        # Extract all file digests from the action's input tree
        input_digests = self._extract_digests_from_action(action)

        # Resolve each digest to an overlay
        for digest in input_digests:
            overlay = self._resolve_digest_to_overlay(digest, element)
            if overlay:
                spec_action.overlays.append(overlay)

        return spec_action if spec_action.overlays else None

    def _extract_digests_from_action(self, action):
        """
        Extract all unique file digests from an Action's input tree.

        Args:
            action: Action proto

        Returns:
            Set of file digests (as Digest protos)
        """
        digests = set()

        if not action.HasField("input_root_digest"):
            return digests

        # Traverse the input root directory tree
        self._collect_file_digests(action.input_root_digest, digests)

        return digests

    def _collect_file_digests(self, directory_digest, digests_set):
        """
        Recursively collect all file digests from a directory tree.

        Args:
            directory_digest: Directory digest to traverse
            digests_set: Set to add found digests to
        """
        try:
            directory = self._cas.fetch_directory_proto(directory_digest)
            if not directory:
                return

            # Collect file digests
            for file_node in directory.files:
                # Store the digest as a tuple (hash, size) for set uniqueness
                digests_set.add((file_node.digest.hash, file_node.digest.size_bytes))

            # Recursively traverse subdirectories
            for dir_node in directory.directories:
                self._collect_file_digests(dir_node.digest, digests_set)
        except:
            pass

    def _resolve_digest_to_overlay(self, digest_tuple, element, artifact_file_path=None):
        """
        Resolve a file digest to an Overlay proto.

        Args:
            digest_tuple: Tuple of (hash, size_bytes)
            element: The element being processed
            artifact_file_path: Path in artifact (used for artifact_overlays), can differ from source_path

        Returns:
            Overlay proto or None if digest cannot be resolved
        """
        from .._protos.buildstream.v2 import speculative_actions_pb2
        from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2

        digest_hash = digest_tuple[0]
        digest_size = digest_tuple[1]

        # Look up in our digest cache
        if digest_hash not in self._digest_cache:
            return None

        element_name, file_path, overlay_type = self._digest_cache[digest_hash]

        # Create overlay
        overlay = speculative_actions_pb2.SpeculativeActions.Overlay()
        overlay.target_digest.hash = digest_hash
        overlay.target_digest.size_bytes = digest_size
        overlay.source_path = file_path  # Path in the source/artifact where it originated

        if overlay_type == "SOURCE":
            overlay.type = speculative_actions_pb2.SpeculativeActions.Overlay.SOURCE
            # Empty string means self-reference for this element
            overlay.source_element = "" if element_name == element.name else element_name
        elif overlay_type == "ARTIFACT":
            overlay.type = speculative_actions_pb2.SpeculativeActions.Overlay.ARTIFACT
            overlay.source_element = element_name
        else:
            return None

        return overlay

    def _generate_artifact_overlays(self, element):
        """
        Generate artifact_overlays for the element's output files.

        This creates a mapping from artifact file digests back to their
        sources, enabling downstream elements to trace dependencies.

        Args:
            element: The element with the artifact

        Returns:
            List of Overlay protos
        """
        overlays = []

        try:
            # Check if element is cached
            if not element._cached():
                return overlays

            # Get the artifact object
            artifact = element._get_artifact()
            if not artifact or not artifact.cached():
                return overlays

            # Get the artifact files directory
            files_dir = artifact.get_files()
            if not files_dir:
                return overlays

            # Traverse artifact files and create overlays for each
            self._generate_overlays_for_directory(
                files_dir._get_digest(), element, overlays, ""  # Start with empty path
            )
        except Exception as e:
            pass

        return overlays

    def _generate_overlays_for_directory(self, directory_digest, element, overlays, current_path):
        """
        Recursively generate overlays for files in a directory.

        Args:
            directory_digest: Directory to process
            element: The element being processed
            overlays: List to append overlays to
            current_path: Current relative path from root
        """
        try:
            directory = self._cas.fetch_directory_proto(directory_digest)
            if not directory:
                return

            # Process each file with full path
            for file_node in directory.files:
                file_path = file_node.name if not current_path else f"{current_path}/{file_node.name}"
                overlay = self._resolve_digest_to_overlay(
                    (file_node.digest.hash, file_node.digest.size_bytes), element, file_path
                )
                if overlay:
                    overlays.append(overlay)

            # Recursively process subdirectories
            for dir_node in directory.directories:
                subdir_path = dir_node.name if not current_path else f"{current_path}/{dir_node.name}"
                self._generate_overlays_for_directory(dir_node.digest, element, overlays, subdir_path)
        except Exception as e:
            pass
