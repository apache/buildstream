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
SpeculativeActionGenerationQueue
=================================

Queue for generating SpeculativeActions after element builds.

This queue runs after BuildQueue to:
1. Extract subaction digests from built elements
2. Generate SOURCE and ARTIFACT overlays
3. Store SpeculativeActions with the artifact
"""

# Local imports
from . import Queue, QueueStatus
from ..jobs import JobStatus


# A queue which generates speculative actions for built elements
#
class SpeculativeActionGenerationQueue(Queue):

    action_name = "Generating overlays"
    complete_name = "Overlays generated"
    resources = []  # No special resources needed

    def get_process_func(self):
        return SpeculativeActionGenerationQueue._generate_overlays

    def status(self, element):
        # Only process elements that were successfully built
        # and have subaction digests
        if not element._cached_success():
            return QueueStatus.SKIP

        # Check if element has subaction digests
        subaction_digests = element._get_subaction_digests()
        if not subaction_digests:
            return QueueStatus.SKIP

        return QueueStatus.READY

    def done(self, _, element, result, status):
        if status is JobStatus.FAIL:
            # Generation is best-effort, don't fail the build
            pass

        # Result contains the SpeculativeActions that were generated
        # The artifact cache has already been updated in the child process

    @staticmethod
    def _generate_overlays(element):
        """
        Generate SpeculativeActions for an element.

        Args:
            element: The element to generate overlays for

        Returns:
            Number of actions generated, or None if skipped
        """
        from ..._speculative_actions.generator import SpeculativeActionsGenerator

        # Get subaction digests
        subaction_digests = element._get_subaction_digests()
        if not subaction_digests:
            return None

        # Get the context and caches
        context = element._get_context()
        cas = context.get_cascache()
        artifactcache = context.artifactcache

        # Get dependencies to resolve overlays
        from ...types import _Scope

        dependencies = list(element._dependencies(_Scope.BUILD, recurse=False))

        # Get action cache service for ACTION overlay generation
        casd = context.get_casd()
        ac_service = casd.get_ac_service() if casd else None

        # Generate overlays
        generator = SpeculativeActionsGenerator(cas, ac_service=ac_service, artifactcache=artifactcache)
        spec_actions = generator.generate_speculative_actions(element, subaction_digests, dependencies)

        if not spec_actions or not spec_actions.actions:
            return 0

        # Store with the artifact, using weak key for stable lookup
        artifact = element._get_artifact()
        weak_key = element._get_weak_cache_key()
        artifactcache.store_speculative_actions(artifact, spec_actions, weak_key=weak_key)

        return len(spec_actions.actions)
