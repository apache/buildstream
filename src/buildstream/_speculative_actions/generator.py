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
3. Resolving digests to their source elements (SOURCE > ACTION > ARTIFACT priority)
4. Creating overlays for each digest
5. Generating artifact_overlays for the element's output files
6. Tracking inter-subaction output dependencies via ACTION overlays
"""

from typing import Dict, Tuple


class SpeculativeActionsGenerator:
    """
    Generates SpeculativeActions from element builds.

    This class analyzes completed element builds to extract subactions and
    generate overlay metadata that describes how to adapt inputs for future
    builds.
    """

    def __init__(self, cas, ac_service=None, artifactcache=None):
        """
        Initialize the generator.

        Args:
            cas: The CAS cache for fetching actions and directories
            ac_service: Optional ActionCache service stub for fetching
                ActionResults of prior subactions (needed for ACTION overlays)
            artifactcache: Optional artifact cache for loading dependency
                SpeculativeActions (needed for cross-element ACTION overlays)
        """
        self._cas = cas
        self._ac_service = ac_service
        self._artifactcache = artifactcache
        # Cache for digest.hash -> list of (element, path, type) lookups
        # Multiple entries per digest enable fallback resolution:
        # SOURCE overlays are tried first, then ACTION, then ARTIFACT.
        self._digest_cache: Dict[str, list] = {}
        # Artifact file entries for the element being processed,
        # collected during _build_digest_cache to avoid re-traversal
        # in _generate_artifact_overlays.
        # List of (digest_hash, digest_size) tuples.
        self._own_artifact_entries: list = []

    def generate_speculative_actions(self, element, subaction_digests, dependencies, mode=None):
        """
        Generate SpeculativeActions for an element build.

        This is the main entry point for overlay generation. It processes
        all subactions from the element's build and generates overlays
        for each.

        Args:
            element: The element that was built
            subaction_digests: List of Action digests from the build (from ActionResult.subactions)
            dependencies: List of dependency elements (for resolving artifact overlays)
            mode: _SpeculativeActionMode controlling which overlay types to generate.
                None defaults to FULL for backward compatibility.

        Returns:
            A SpeculativeActions message containing:
            - actions: SpeculativeActions with overlays for each subaction
            - artifact_overlays: Overlays mapping artifact file digests to sources
        """
        from .._protos.buildstream.v2 import speculative_actions_pb2
        from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
        from ..types import _SpeculativeActionMode

        if mode is None:
            mode = _SpeculativeActionMode.FULL

        spec_actions = speculative_actions_pb2.SpeculativeActions()

        # Build digest lookup tables from element sources and dependencies
        self._build_digest_cache(element, dependencies)

        # Track outputs from prior subactions for ACTION overlay generation
        # Maps file_digest_hash -> (source_element, producing_action_digest, output_path)
        prior_outputs = {}

        # Seed prior_outputs with dependency subaction outputs for
        # cross-element ACTION overlays (full mode only).
        # These enable earlier resolution than ARTIFACT overlays: an
        # ACTION overlay resolves when the dep is primed (via
        # instantiated_actions), while an ARTIFACT overlay only resolves
        # when the dep is fully built.  This parallelism is the core
        # benefit of speculative actions.
        if mode == _SpeculativeActionMode.FULL:
            if self._ac_service and self._artifactcache:
                self._seed_dependency_outputs(dependencies, prior_outputs)

        # Generate overlays for each subaction
        for subaction_digest in subaction_digests:
            spec_action, input_digests = self._generate_action_overlays(element, subaction_digest)

            # Generate ACTION overlays for digests that match prior subaction outputs
            # but weren't already resolved as SOURCE or ARTIFACT.
            # Requires intra-element or full mode.
            if mode in (_SpeculativeActionMode.INTRA_ELEMENT, _SpeculativeActionMode.FULL):
                if self._ac_service and prior_outputs and input_digests:
                    # Collect hashes already covered by SOURCE/ARTIFACT overlays
                    already_overlaid = set()
                    if spec_action:
                        for overlay in spec_action.overlays:
                            already_overlaid.add(overlay.target_digest.hash)

                    for digest_hash, digest_size in input_digests:
                        if digest_hash in prior_outputs and digest_hash not in already_overlaid:
                            source_element, producing_action_digest, output_path = prior_outputs[digest_hash]
                            # Create ACTION overlay
                            if spec_action is None:
                                spec_action = speculative_actions_pb2.SpeculativeActions.SpeculativeAction()
                                spec_action.base_action_digest.CopyFrom(subaction_digest)
                            overlay = speculative_actions_pb2.SpeculativeActions.Overlay()
                            overlay.type = speculative_actions_pb2.SpeculativeActions.Overlay.ACTION
                            overlay.source_element = source_element
                            overlay.source_action_digest.CopyFrom(producing_action_digest)
                            overlay.source_path = output_path
                            overlay.target_digest.hash = digest_hash
                            overlay.target_digest.size_bytes = digest_size
                            spec_action.overlays.append(overlay)

            # Sort overlays: SOURCE > ACTION > ARTIFACT
            # This ensures the instantiator tries SOURCE first, then
            # ACTION (intermediate files), then ARTIFACT as fallback.
            if spec_action:
                type_priority = {
                    speculative_actions_pb2.SpeculativeActions.Overlay.SOURCE: 0,
                    speculative_actions_pb2.SpeculativeActions.Overlay.ACTION: 1,
                    speculative_actions_pb2.SpeculativeActions.Overlay.ARTIFACT: 2,
                }
                spec_action.overlays.sort(key=lambda o: type_priority.get(o.type, 99))
                spec_actions.actions.append(spec_action)

            # Fetch this subaction's ActionResult and record its outputs
            # for subsequent subactions (intra-element and full modes)
            if mode in (_SpeculativeActionMode.INTRA_ELEMENT, _SpeculativeActionMode.FULL):
                if self._ac_service:
                    self._record_subaction_outputs(subaction_digest, prior_outputs)

        # Generate artifact overlays for the element's output files
        artifact_overlays = self._generate_artifact_overlays(element)
        spec_actions.artifact_overlays.extend(artifact_overlays)

        return spec_actions

    def _record_subaction_outputs(self, action_digest, prior_outputs, source_element=""):
        """
        Fetch a subaction's ActionResult from the action cache and record
        its output file digests for subsequent subaction ACTION overlay generation.

        Args:
            action_digest: The action digest to look up (stored on ACTION overlays)
            prior_outputs: Dict to update with file_digest_hash -> (source_element, action_digest, path)
            source_element: Element name for cross-element overlays ("" = same element)
        """
        try:
            from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2

            request = remote_execution_pb2.GetActionResultRequest(
                action_digest=action_digest,
            )
            action_result = self._ac_service.GetActionResult(request)
            if action_result:
                for output_file in action_result.output_files:
                    prior_outputs[output_file.digest.hash] = (
                        source_element, action_digest, output_file.path
                    )
        except Exception:
            pass

    def _seed_dependency_outputs(self, dependencies, prior_outputs):
        """
        Seed prior_outputs with subaction outputs from dependency elements.

        For each dependency that has stored SpeculativeActions, fetch the
        ActionResult of each subaction and record its output files.  This
        enables cross-element ACTION overlays: if the current element's
        subaction input tree contains a file that was produced by a
        dependency's subaction, the overlay will reference it.

        Cross-element ACTION overlays enable earlier resolution than
        ARTIFACT overlays: they resolve when the dep is primed (via
        instantiated_actions), while ARTIFACT overlays only resolve
        when the dep is fully built.

        Args:
            dependencies: List of dependency elements
            prior_outputs: Dict to seed with file_digest_hash ->
                (source_element, action_digest, path)
        """
        for dep in dependencies:
            try:
                if not dep._cached():
                    continue

                artifact = dep._get_artifact()
                if not artifact or not artifact.cached():
                    continue

                dep_sa = self._artifactcache.get_speculative_actions(artifact)
                if not dep_sa:
                    continue

                for spec_action in dep_sa.actions:
                    self._record_subaction_outputs(
                        spec_action.base_action_digest,
                        prior_outputs,
                        source_element=dep.name,
                    )
            except Exception:
                pass

    def _build_digest_cache(self, element, dependencies):
        """
        Build a cache mapping file digests to their source elements.

        Multiple entries per digest are stored to enable fallback
        resolution at instantiation time (SOURCE > ACTION > ARTIFACT).

        Args:
            element: The element being processed
            dependencies: List of dependency elements
        """
        self._digest_cache.clear()
        self._own_artifact_entries.clear()

        # Index element's own sources (highest priority)
        self._index_element_sources(element, element)

        # Index dependency sources — enables SOURCE overlays for dep
        # files (e.g. headers) that exist in both source and artifact.
        # At instantiation, SOURCE is tried first; if the dep's sources
        # aren't fetched (dep not rebuilding), ARTIFACT is used instead.
        for dep in dependencies:
            self._index_element_sources(dep, dep)

        # Index dependency artifacts
        for dep in dependencies:
            self._index_element_artifact(dep)

        # Index element's own artifact and collect entries for
        # artifact_overlays generation (avoids re-traversal later)
        self._index_element_artifact(element, collect_entries=True)

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

    def _index_element_artifact(self, element, collect_entries=False):
        """
        Index all file digests in an element's artifact output.

        Args:
            element: The element whose artifact to index
            collect_entries: If True, also collect (digest_hash, digest_size)
                tuples in self._own_artifact_entries for artifact_overlays
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
                files_dir._get_digest(), element.name, "ARTIFACT", "",
                collect_entries=collect_entries,
            )
        except Exception as e:
            # Gracefully handle missing artifacts
            pass

    def _traverse_directory_with_paths(self, directory_digest, element_name, overlay_type, current_path,
                                       collect_entries=False):
        """
        Recursively traverse a Directory tree and index all file digests with full paths.

        Args:
            directory_digest: The Directory digest to traverse
            element_name: The element name to associate with found files
            overlay_type: Either "SOURCE" or "ARTIFACT"
            current_path: Current relative path from root (e.g., "src/foo")
            collect_entries: If True, also append to self._own_artifact_entries
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

                entry = (element_name, file_path, overlay_type)
                if digest_hash not in self._digest_cache:
                    self._digest_cache[digest_hash] = [entry]
                else:
                    # Avoid duplicate (same element, same path, same type)
                    if entry not in self._digest_cache[digest_hash]:
                        self._digest_cache[digest_hash].append(entry)

                if collect_entries:
                    self._own_artifact_entries.append(
                        (digest_hash, file_node.digest.size_bytes)
                    )

            # Recursively traverse subdirectories
            for dir_node in directory.directories:
                # Build path for subdirectory
                subdir_path = dir_node.name if not current_path else f"{current_path}/{dir_node.name}"
                self._traverse_directory_with_paths(
                    dir_node.digest, element_name, overlay_type, subdir_path,
                    collect_entries=collect_entries,
                )
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
            Tuple of (SpeculativeAction proto or None, input_digests set)
        """
        from .._protos.buildstream.v2 import speculative_actions_pb2

        # Fetch the action from CAS
        action = self._cas.fetch_action(action_digest)
        if not action:
            return None, set()

        spec_action = speculative_actions_pb2.SpeculativeActions.SpeculativeAction()
        spec_action.base_action_digest.CopyFrom(action_digest)

        # Extract all file digests from the action's input tree
        input_digests = self._extract_digests_from_action(action)

        # Resolve each digest to overlays (may produce multiple per digest
        # for fallback resolution: SOURCE > ACTION > ARTIFACT)
        for digest in input_digests:
            overlays = self._resolve_digest_to_overlays(digest, element)
            spec_action.overlays.extend(overlays)

        return (spec_action if spec_action.overlays else None), input_digests

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

    def _resolve_digest_to_overlays(self, digest_tuple, element):
        """
        Resolve a file digest to Overlay protos.

        Returns multiple overlays when the same digest appears in both
        source and artifact trees, enabling fallback resolution at
        instantiation time (SOURCE tried first, then ARTIFACT).

        Args:
            digest_tuple: Tuple of (hash, size_bytes)
            element: The element being processed

        Returns:
            List of Overlay protos (SOURCE first, then ARTIFACT), or empty list
        """
        from .._protos.buildstream.v2 import speculative_actions_pb2

        digest_hash = digest_tuple[0]
        digest_size = digest_tuple[1]

        entries = self._digest_cache.get(digest_hash)
        if not entries:
            return []

        overlays = []
        for element_name, file_path, overlay_type in entries:
            overlay = speculative_actions_pb2.SpeculativeActions.Overlay()
            overlay.target_digest.hash = digest_hash
            overlay.target_digest.size_bytes = digest_size
            overlay.source_path = file_path

            if overlay_type == "SOURCE":
                overlay.type = speculative_actions_pb2.SpeculativeActions.Overlay.SOURCE
                overlay.source_element = "" if element_name == element.name else element_name
            elif overlay_type == "ARTIFACT":
                overlay.type = speculative_actions_pb2.SpeculativeActions.Overlay.ARTIFACT
                overlay.source_element = element_name
            else:
                continue

            overlays.append(overlay)

        # Sort: SOURCE first, then ARTIFACT — instantiator tries in order.
        # ACTION overlays are added separately in generate_speculative_actions()
        # and the final sort there establishes SOURCE > ACTION > ARTIFACT.
        type_priority = {
            speculative_actions_pb2.SpeculativeActions.Overlay.SOURCE: 0,
            speculative_actions_pb2.SpeculativeActions.Overlay.ARTIFACT: 2,
        }
        overlays.sort(key=lambda o: type_priority.get(o.type, 99))

        return overlays

    def _generate_artifact_overlays(self, element):
        """
        Generate artifact_overlays for the element's output files.

        Uses _own_artifact_entries collected during _build_digest_cache
        to avoid re-traversing the artifact tree.

        Args:
            element: The element with the artifact

        Returns:
            List of Overlay protos
        """
        overlays = []
        for digest_hash, digest_size in self._own_artifact_entries:
            resolved = self._resolve_digest_to_overlays(
                (digest_hash, digest_size), element
            )
            # For artifact_overlays, take the highest-priority overlay
            if resolved:
                overlays.append(resolved[0])
        return overlays
