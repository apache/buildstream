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
SpeculativeCachePrimingQueue
=============================

Queue for priming the remote ActionCache with speculative actions.

This queue runs after PullQueue (in parallel with BuildQueue) to:
1. Retrieve SpeculativeActions from pulled artifacts
2. Instantiate actions by applying overlays
3. Submit to execution via buildbox-casd to prime the ActionCache

This enables parallelism: while elements build normally, we're priming
the cache for other elements that will build later.
"""

# Local imports
from . import Queue, QueueStatus
from ..jobs import JobStatus
from ..resources import ResourceType


# A queue which primes the ActionCache with speculative actions
#
class SpeculativeCachePrimingQueue(Queue):

    action_name = "Priming cache"
    complete_name = "Cache primed"
    resources = [ResourceType.UPLOAD]  # Uses network to submit actions

    def get_process_func(self):
        return SpeculativeCachePrimingQueue._prime_cache

    def status(self, element):
        # Only process elements that were pulled (not built locally)
        # and are cached with SpeculativeActions
        if not element._cached():
            return QueueStatus.SKIP

        # Check if element has SpeculativeActions (try weak key first)
        context = element._get_context()
        artifactcache = context.artifactcache
        artifact = element._get_artifact()
        weak_key = element._get_weak_cache_key()

        spec_actions = artifactcache.get_speculative_actions(artifact, weak_key=weak_key)
        if not spec_actions or not spec_actions.actions:
            return QueueStatus.SKIP

        return QueueStatus.READY

    def done(self, _, element, result, status):
        if status is JobStatus.FAIL:
            # Priming is best-effort, don't fail the build
            return

        # Result contains number of actions submitted
        if result:
            primed_count, total_count = result
            element.info(f"Primed {primed_count}/{total_count} actions")

    @staticmethod
    def _prime_cache(element):
        """
        Prime the ActionCache for an element.

        Retrieves stored SpeculativeActions, instantiates them with
        current dependency digests, and submits each adapted action
        to buildbox-casd's execution service. The execution produces
        verified ActionResults that get cached, so subsequent builds
        can hit the action cache instead of rebuilding.

        Args:
            element: The element to prime cache for

        Returns:
            Tuple of (primed_count, total_count) or None if skipped
        """
        from ..._speculative_actions.instantiator import SpeculativeActionInstantiator

        # Get the context and caches
        context = element._get_context()
        cas = context.get_cascache()
        artifactcache = context.artifactcache

        # Get SpeculativeActions (try weak key first)
        artifact = element._get_artifact()
        weak_key = element._get_weak_cache_key()
        spec_actions = artifactcache.get_speculative_actions(artifact, weak_key=weak_key)
        if not spec_actions or not spec_actions.actions:
            return None

        # Build element lookup for dependency resolution
        from ...types import _Scope

        dependencies = list(element._dependencies(_Scope.BUILD, recurse=True))
        element_lookup = {dep.name: dep for dep in dependencies}
        element_lookup[element.name] = element  # Include self

        # Instantiate and submit each action
        instantiator = SpeculativeActionInstantiator(cas, artifactcache)
        primed_count = 0
        total_count = len(spec_actions.actions)

        # Get the execution service from buildbox-casd
        casd = context.get_casd()
        exec_service = casd._exec_service
        if not exec_service:
            element.warn("No execution service available for speculative action priming")
            return None

        for spec_action in spec_actions.actions:
            try:
                # Instantiate action by applying overlays
                action_digest = instantiator.instantiate_action(spec_action, element, element_lookup)

                if not action_digest:
                    continue

                # Submit to buildbox-casd's execution service.
                # casd runs the action via its local execution scheduler
                # (buildbox-run), producing a verified ActionResult that
                # gets stored in the action cache.
                if SpeculativeCachePrimingQueue._submit_action(
                    exec_service, action_digest, element
                ):
                    primed_count += 1

            except Exception as e:
                # Best-effort: log but continue with other actions
                element.warn(f"Failed to prime action: {e}")
                continue

        return (primed_count, total_count)

    @staticmethod
    def _submit_action(exec_service, action_digest, element):
        """
        Submit an action to buildbox-casd's execution service.

        This sends an Execute request to the local buildbox-casd, which
        runs the action via its local execution scheduler (using
        buildbox-run). The resulting ActionResult is stored in the
        action cache, making it available for future builds.

        Args:
            exec_service: The gRPC ExecutionStub for buildbox-casd
            action_digest: The Action digest to execute
            element: The element (for logging)

        Returns:
            bool: True if submitted successfully
        """
        try:
            from ..._protos.build.bazel.remote.execution.v2 import remote_execution_pb2

            request = remote_execution_pb2.ExecuteRequest(
                action_digest=action_digest,
                skip_cache_lookup=False,  # Check ActionCache first
            )

            # Submit Execute request. The response is a stream of
            # Operation messages. We consume the stream to ensure the
            # action completes and the result is cached.
            operation_stream = exec_service.Execute(request)
            for operation in operation_stream:
                if operation.done:
                    # Check if the operation completed successfully
                    if operation.HasField("error"):
                        element.warn(
                            f"Priming action failed: {operation.error.message}"
                        )
                        return False
                    return True

            # Stream ended without a done operation
            return False

        except Exception as e:
            element.warn(f"Failed to submit priming action: {e}")
            return False
