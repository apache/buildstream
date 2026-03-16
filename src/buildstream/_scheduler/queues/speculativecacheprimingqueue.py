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

Queue for priming the ActionCache with speculative actions.

This queue runs BEFORE BuildQueue to aggressively front-run builds:
1. For each element that needs building, check if SpeculativeActions
   from a previous build are stored under the element's weak key
2. Ensure all needed CAS blobs are local (single FetchMissingBlobs call)
3. Instantiate actions by applying overlays with current dependency digests
4. Submit to execution via buildbox-casd to produce verified ActionResults
5. The results are cached so when recc (or the build) later needs the
   same action, it gets an ActionCache hit instead of rebuilding
"""

# Local imports
from . import Queue, QueueStatus
from ..jobs import JobStatus
from ..resources import ResourceType


class SpeculativeCachePrimingQueue(Queue):

    action_name = "Priming cache"
    complete_name = "Cache primed"
    resources = [ResourceType.UPLOAD]

    def get_process_func(self):
        return SpeculativeCachePrimingQueue._prime_cache

    def status(self, element):
        # Prime elements that are NOT cached (will need building) and
        # have stored SpeculativeActions from a previous build.
        if element._cached():
            return QueueStatus.SKIP

        weak_key = element._get_weak_cache_key()
        if not weak_key:
            return QueueStatus.SKIP

        context = element._get_context()
        artifactcache = context.artifactcache
        spec_actions = artifactcache.lookup_speculative_actions_by_weak_key(element, weak_key)
        if not spec_actions or not spec_actions.actions:
            return QueueStatus.SKIP

        return QueueStatus.READY

    def done(self, _, element, result, status):
        if status is JobStatus.FAIL:
            return

        if result:
            primed_count, total_count = result
            element.info(f"Primed {primed_count}/{total_count} actions")

    @staticmethod
    def _prime_cache(element):
        from ..._speculative_actions.instantiator import SpeculativeActionInstantiator

        context = element._get_context()
        cas = context.get_cascache()
        artifactcache = context.artifactcache

        # Get SpeculativeActions by weak key
        weak_key = element._get_weak_cache_key()
        spec_actions = artifactcache.lookup_speculative_actions_by_weak_key(element, weak_key)
        if not spec_actions or not spec_actions.actions:
            return None

        # Pre-fetch all CAS blobs needed for instantiation so the
        # instantiator runs entirely from local CAS without round-trips.
        #
        # Phase 1: Fetch all base Action protos in one FetchMissingBlobs batch
        # Phase 2: For each action, fetch its entire input tree via FetchTree
        project = element._get_project()
        _, storage_remotes = artifactcache.get_remotes(project.name, False)
        remote = storage_remotes[0] if storage_remotes else None

        if remote:
            from ..._protos.build.bazel.remote.execution.v2 import remote_execution_pb2

            # Phase 1: batch-fetch all base Action protos
            base_action_digests = [
                sa.base_action_digest
                for sa in spec_actions.actions
                if sa.base_action_digest.hash
            ]
            if base_action_digests:
                try:
                    cas.fetch_blobs(remote, base_action_digests, allow_partial=True)
                except Exception:
                    pass  # Best-effort

            # Phase 2: fetch input trees for each base action
            for digest in base_action_digests:
                try:
                    action = cas.fetch_action(digest)
                    if action and action.HasField("input_root_digest"):
                        cas.fetch_directory(remote, action.input_root_digest)
                except Exception:
                    pass  # Best-effort; instantiator skips actions it can't resolve

        # Build element lookup for dependency resolution
        from ...types import _Scope

        dependencies = list(element._dependencies(_Scope.BUILD, recurse=True))
        element_lookup = {dep.name: dep for dep in dependencies}
        element_lookup[element.name] = element

        # Get execution service
        casd = context.get_casd()
        exec_service = casd.get_exec_service()
        if not exec_service:
            element.warn("No execution service available for speculative action priming")
            return None

        # Instantiate and submit each action
        instantiator = SpeculativeActionInstantiator(cas, artifactcache)
        primed_count = 0
        total_count = len(spec_actions.actions)

        for spec_action in spec_actions.actions:
            try:
                action_digest = instantiator.instantiate_action(spec_action, element, element_lookup)

                if not action_digest:
                    continue

                if SpeculativeCachePrimingQueue._submit_action(
                    exec_service, action_digest, element
                ):
                    primed_count += 1

            except Exception as e:
                element.warn(f"Failed to prime action: {e}")
                continue

        return (primed_count, total_count)

    @staticmethod
    def _submit_action(exec_service, action_digest, element):
        try:
            from ..._protos.build.bazel.remote.execution.v2 import remote_execution_pb2

            request = remote_execution_pb2.ExecuteRequest(
                action_digest=action_digest,
                skip_cache_lookup=False,
            )

            operation_stream = exec_service.Execute(request)
            for operation in operation_stream:
                if operation.done:
                    if operation.HasField("error"):
                        element.warn(
                            f"Priming action failed: {operation.error.message}"
                        )
                        return False
                    return True

            return False

        except Exception as e:
            element.warn(f"Failed to submit priming action: {e}")
            return False
