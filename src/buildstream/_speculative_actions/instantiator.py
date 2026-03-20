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
SpeculativeActionInstantiator
==============================

Instantiates SpeculativeActions by applying overlays.

This module is responsible for:
1. Checking if the action is already instantiated (via global instantiated_actions)
2. Fetching base actions from CAS
3. Applying SOURCE, ACTION, and ARTIFACT overlays (in that priority order)
4. Replacing file digests in action input trees
5. Storing modified actions back to CAS
"""




class SpeculativeActionInstantiator:
    """
    Instantiate SpeculativeActions by applying overlays.

    This class takes speculative actions and adapts them to current
    dependency versions by replacing file digests according to overlays.
    """

    def __init__(self, cas, artifactcache, ac_service=None):
        """
        Initialize the instantiator.

        Args:
            cas: The CAS cache
            artifactcache: The artifact cache
            ac_service: Optional ActionCache service stub for resolving
                cross-element ACTION overlays
        """
        self._cas = cas
        self._artifactcache = artifactcache
        self._ac_service = ac_service

    def instantiate_action(self, spec_action, element, element_lookup,
                           instantiated_actions=None, resolved_cache=None):
        """
        Instantiate a SpeculativeAction by applying overlays.

        Previously resolved overlays can be passed in via resolved_cache
        to avoid re-resolving overlays that succeeded on a prior pass but
        whose SA couldn't be fully instantiated yet (e.g. an ACTION
        overlay was deferred).

        Args:
            spec_action: SpeculativeAction proto (may be mutated: overlays
                removed by the priming queue)
            element: Element being primed
            element_lookup: Dict mapping element names to Element objects
            instantiated_actions: Optional dict mapping base_action_hash -> adapted_action_digest
                (global across all elements, populated by the priming queue)
            resolved_cache: Optional dict of {target_digest_hash -> new_digest}
                from prior passes, updated in-place with new resolutions

        Returns:
            Digest of instantiated action, or None if overlays cannot be applied
        """
        # Step 0: Check if already instantiated (e.g. by another element's priming)
        base_hash = spec_action.base_action_digest.hash
        if instantiated_actions is not None and base_hash in instantiated_actions:
            return instantiated_actions[base_hash]

        # Fetch the base action
        base_action = self._cas.fetch_action(spec_action.base_action_digest)
        if not base_action:
            return None

        # Get cached build dependency cache keys for optimization
        # Skip overlays for dependencies that haven't changed
        cached_dep_keys = self._get_cached_dependency_keys(element)

        # Start with a copy of the base action
        from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2

        action = remote_execution_pb2.Action()
        action.CopyFrom(base_action)

        # Seed digest_replacements from the resolution cache (if provided).
        # This avoids re-resolving overlays that succeeded on a prior
        # pass but whose SA couldn't be fully instantiated yet.
        if resolved_cache is None:
            resolved_cache = {}
        digest_replacements = dict(resolved_cache)
        skipped_count = 0
        applied_count = 0

        # Resolve overlays with fallback.  Multiple overlays may target
        # the same digest (e.g. SOURCE + ARTIFACT for the same dep file).
        # They are stored in priority order (SOURCE first); once a target
        # is resolved, subsequent overlays for it are skipped.
        for overlay in spec_action.overlays:
            # Skip if this target was already resolved (by a higher-priority
            # overlay or from the resolution cache)
            if overlay.target_digest.hash in digest_replacements:
                continue

            # Optimization: Skip overlays for dependencies with unchanged cache keys
            # (only applies to SOURCE/ARTIFACT overlays with a source_element)
            if overlay.source_element and self._should_skip_overlay(overlay, element, cached_dep_keys):
                skipped_count += 1
                continue

            replacement = self._resolve_overlay(overlay, element, element_lookup, instantiated_actions=instantiated_actions)
            if replacement:
                # replacement is (old_digest, new_digest)
                digest_replacements[replacement[0].hash] = replacement[1]
                applied_count += 1

        # Update the resolution cache in-place for the next pass
        resolved_cache.update(digest_replacements)

        # Check if any replacements actually change a digest
        modified = any(
            old_hash != new_digest.hash
            for old_hash, new_digest in digest_replacements.items()
        )

        # Log optimization results
        if skipped_count > 0:
            element.info(f"Skipped {skipped_count} overlays (unchanged dependencies), applied {applied_count}")

        if not modified:
            # No changes needed, return base action digest
            return spec_action.base_action_digest

        # Apply digest replacements to the action's input tree
        if action.HasField("input_root_digest"):
            new_root_digest = self._replace_digests_in_tree(action.input_root_digest, digest_replacements)
            if new_root_digest:
                action.input_root_digest.CopyFrom(new_root_digest)

        # Store the modified action and return its digest
        return self._cas.store_action(action)

    def _get_cached_dependency_keys(self, element):
        """
        Get cache keys for build dependencies from the cached artifact.

        Args:
            element: The element being primed

        Returns:
            Dict mapping element_name -> cache_key from artifact.build_deps
        """
        dep_keys = {}

        try:
            artifact = element._get_artifact()
            if not artifact or not artifact.cached():
                return dep_keys

            artifact_proto = artifact._get_proto()
            if not artifact_proto:
                return dep_keys

            # Extract cache keys from build_deps
            for build_dep in artifact_proto.build_deps:
                dep_keys[build_dep.element_name] = build_dep.cache_key

        except Exception:
            # If we can't get the keys, just continue without optimization
            pass

        return dep_keys

    def _should_skip_overlay(self, overlay, element, cached_dep_keys):
        """
        Check if an overlay can be skipped because the dependency hasn't changed.

        Args:
            overlay: Overlay proto
            element: Element being primed
            cached_dep_keys: Dict of element_name -> cache_key from cached artifact

        Returns:
            bool: True if overlay can be skipped
        """
        from .._protos.buildstream.v2 import speculative_actions_pb2

        # Never skip ACTION overlays via this optimization — they use
        # subaction indices, not element names
        if overlay.type == speculative_actions_pb2.SpeculativeActions.Overlay.ACTION:
            return False

        # Only skip for dependency overlays (source_element is not empty and not self)
        if not overlay.source_element or overlay.source_element == element.name:
            return False

        # Check if we have a cached key for this dependency
        cached_key = cached_dep_keys.get(overlay.source_element)
        if not cached_key:
            return False

        # Get the current dependency element
        from ..types import _Scope

        for dep in element._dependencies(_Scope.BUILD, recurse=False):
            if dep.name == overlay.source_element:
                current_key = dep._get_cache_key()
                # Skip overlay if cache keys match (dependency unchanged)
                if current_key == cached_key:
                    return True
                break

        return False

    def _resolve_overlay(self, overlay, element, element_lookup, instantiated_actions=None):
        """
        Resolve an overlay to get current file digest.

        Args:
            overlay: Overlay proto
            element: Current element
            element_lookup: Dict mapping element names to Element objects
            instantiated_actions: Optional dict mapping base_action_hash -> adapted_action_digest

        Returns:
            Tuple of (old_digest, new_digest) or None
        """
        from .._protos.buildstream.v2 import speculative_actions_pb2

        if overlay.type == speculative_actions_pb2.SpeculativeActions.Overlay.SOURCE:
            return self._resolve_source_overlay(overlay, element, element_lookup)
        elif overlay.type == speculative_actions_pb2.SpeculativeActions.Overlay.ACTION:
            return self._resolve_action_overlay(overlay, instantiated_actions)
        elif overlay.type == speculative_actions_pb2.SpeculativeActions.Overlay.ARTIFACT:
            return self._resolve_artifact_overlay(overlay, element, element_lookup)

        return None

    def _resolve_source_overlay(self, overlay, element, element_lookup):
        """
        Resolve a SOURCE overlay to get current source file digest.

        Args:
            overlay: Overlay proto
            element: Current element
            element_lookup: Dict mapping element names to Element objects

        Returns:
            Tuple of (old_digest, new_digest) or None
        """
        # Determine source element (empty = self)
        if overlay.source_element == "":
            source_element = element
        else:
            # Look up the source element by name
            source_element = element_lookup.get(overlay.source_element)
            if not source_element:
                return None

        # Get current digest from source files
        try:
            # Check if element has any sources
            if not any(source_element.sources()):
                return None

            # Access the private __sources attribute
            sources = source_element._Element__sources
            if not sources or not sources.cached():
                return None

            source_dir = sources.get_files()
            if not source_dir:
                return None

            # Find the file in the source tree by full path
            current_digest = self._find_file_by_path(source_dir._get_digest(), overlay.source_path)

            if current_digest:
                return (overlay.target_digest, current_digest)
        except Exception as e:
            pass

        return None

    def _resolve_artifact_overlay(self, overlay, element, element_lookup):
        """
        Resolve an ARTIFACT overlay to get current artifact file digest.

        Args:
            overlay: Overlay proto
            element: Current element
            element_lookup: Dict mapping element names to Element objects

        Returns:
            Tuple of (old_digest, new_digest) or None
        """
        # Look up the artifact element
        artifact_element = element_lookup.get(overlay.source_element)
        if not artifact_element:
            return None

        try:
            # Check if element is cached
            if not artifact_element._cached():
                return None

            # Get the artifact object
            artifact = artifact_element._get_artifact()
            if not artifact or not artifact.cached():
                return None

            # Get speculative actions to trace back to source
            spec_actions = self._artifactcache.get_speculative_actions(artifact)
            if spec_actions and spec_actions.artifact_overlays:
                # Trace through artifact_overlays to find the ultimate source
                for art_overlay in spec_actions.artifact_overlays:
                    if art_overlay.target_digest.hash == overlay.target_digest.hash:
                        # Found the mapping - now resolve the source overlay
                        return self._resolve_overlay(art_overlay, artifact_element, element_lookup)

            # Fallback: directly look up file in artifact
            files_dir = artifact.get_files()
            if not files_dir:
                return None

            current_digest = self._find_file_by_path(files_dir._get_digest(), overlay.source_path)

            if current_digest:
                return (overlay.target_digest, current_digest)

        except Exception as e:
            pass

        return None

    def _resolve_action_overlay(self, overlay, instantiated_actions):
        """
        Resolve an ACTION overlay using the global instantiated_actions map.

        Looks up the producing subaction's adapted digest in
        instantiated_actions, then fetches the ActionResult from the
        action cache to find the output file's current digest.

        Works for both intra-element and cross-element ACTION overlays,
        since instantiated_actions is global across all elements.

        Args:
            overlay: Overlay proto with type ACTION
            instantiated_actions: Dict mapping base_action_hash -> adapted_action_digest

        Returns:
            Tuple of (old_digest, new_digest) or None
        """
        source_hash = overlay.source_action_digest.hash

        # Step 1: Look up the adapted digest for the producing action
        adapted_digest = None
        if instantiated_actions:
            adapted_digest = instantiated_actions.get(source_hash)

        if adapted_digest is None:
            # Producing action was never instantiated — drop this overlay
            return None

        # Step 2: Fetch ActionResult using the adapted digest from AC
        if self._ac_service:
            try:
                from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2

                request = remote_execution_pb2.GetActionResultRequest(
                    action_digest=adapted_digest,
                )
                action_result = self._ac_service.GetActionResult(request)
                if action_result:
                    for output_file in action_result.output_files:
                        if output_file.path == overlay.source_path:
                            return (overlay.target_digest, output_file.digest)
            except Exception:
                pass

        return None

    def _find_file_by_path(self, directory_digest, file_path):
        """
        Find a file in a directory tree by full relative path.

        Args:
            directory_digest: Directory to search
            file_path: Full relative path (e.g., "src/foo/bar.c")

        Returns:
            File digest or None
        """
        try:
            # Split path into components
            if not file_path:
                return None

            parts = file_path.split("/")
            current_digest = directory_digest

            # Navigate through directories
            for i, part in enumerate(parts[:-1]):  # All but the last (filename)
                directory = self._cas.fetch_directory_proto(current_digest)
                if not directory:
                    return None

                # Find the subdirectory
                found = False
                for dir_node in directory.directories:
                    if dir_node.name == part:
                        current_digest = dir_node.digest
                        found = True
                        break

                if not found:
                    return None

            # Now find the file
            filename = parts[-1]
            directory = self._cas.fetch_directory_proto(current_digest)
            if not directory:
                return None

            for file_node in directory.files:
                if file_node.name == filename:
                    return file_node.digest

        except Exception as e:
            pass

        return None

    def _replace_digests_in_tree(self, directory_digest, replacements):
        """
        Replace file digests in a directory tree.

        Args:
            directory_digest: Root directory digest
            replacements: Dict of old_hash -> new_digest

        Returns:
            New directory digest or None
        """
        try:
            directory = self._cas.fetch_directory_proto(directory_digest)
            if not directory:
                return None

            from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2

            new_directory = remote_execution_pb2.Directory()
            new_directory.CopyFrom(directory)

            modified = False

            # Replace file digests
            for i, file_node in enumerate(new_directory.files):
                if file_node.digest.hash in replacements:
                    new_directory.files[i].digest.CopyFrom(replacements[file_node.digest.hash])
                    modified = True

            # Recursively process subdirectories
            for i, dir_node in enumerate(new_directory.directories):
                new_subdir_digest = self._replace_digests_in_tree(dir_node.digest, replacements)
                if new_subdir_digest and new_subdir_digest.hash != dir_node.digest.hash:
                    new_directory.directories[i].digest.CopyFrom(new_subdir_digest)
                    modified = True

            if modified:
                # Store the modified directory
                return self._cas.store_directory_proto(new_directory)
            else:
                # No changes, return original
                return directory_digest
        except:
            return None
