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

This queue runs BEFORE BuildQueue and uses the PENDING state to hold
elements while their dependencies build.  While an element waits,
background priming runs fire-and-forget — submitting adapted actions
to casd for execution.  As each dependency completes, per-dep callbacks
trigger incremental overlay resolution, unlocking more subactions.

When all dependencies are cached and the element becomes buildable,
a final priming pass resolves remaining ACTION overlays and the
element is released to the BuildQueue.  By then, most adapted actions
are already in the action cache — recc gets cache hits.

Elements without stored SpeculativeActions skip this queue entirely.
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
        # Runs when element is READY (buildable) — final priming pass
        return SpeculativeCachePrimingQueue._final_prime_pass

    def status(self, element):
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

        # Has SAs.  If not buildable, enter PENDING — background
        # priming will run while we wait for dependencies.
        if not element._buildable():
            return QueueStatus.PENDING

        # Already buildable — run final priming pass as a job
        return QueueStatus.READY

    def register_pending_element(self, element):
        # Register per-dep callback for incremental overlay resolution
        element._set_build_dep_cached_callback(self._on_dep_cached)

        # Also register buildable callback so we get re-enqueued
        # when the element becomes fully buildable
        element._set_buildable_callback(self._enqueue_element)

        # Launch background priming immediately in the scheduler's
        # thread pool — fire-and-forget independent subactions while
        # we wait for dependencies
        self._scheduler.loop.call_soon(self._launch_background_priming, element)

    def _launch_background_priming(self, element):
        self._scheduler.loop.run_in_executor(
            None, SpeculativeCachePrimingQueue._background_prime, element
        )

    def _on_dep_cached(self, element, dep):
        """Called each time a build dependency of element becomes cached.

        Launches incremental priming in the background — newly resolvable
        ARTIFACT overlays (dep's artifact now cached) and ACTION overlays
        (dep's subaction results now in AC) can be resolved and submitted.
        """
        self._scheduler.loop.call_soon(
            self._launch_incremental_prime, element, dep
        )

    def _launch_incremental_prime(self, element, dep):
        self._scheduler.loop.run_in_executor(
            None, SpeculativeCachePrimingQueue._incremental_prime, element, dep
        )

    def done(self, _, element, result, status):
        if status is JobStatus.FAIL:
            return

        if result:
            primed, skipped, total = result
            if skipped:
                element.info(f"Primed {primed}/{total} actions ({skipped} skipped)")
            else:
                element.info(f"Primed {primed}/{total} actions")

        # Clear priming state and per-dep callback
        element._set_build_dep_cached_callback(None)
        element.__priming_submitted = None
        element.__priming_action_outputs = None
        element.__priming_adapted_digests = None

    # -----------------------------------------------------------------
    # Background priming (runs in thread pool while element is PENDING)
    # -----------------------------------------------------------------

    @staticmethod
    def _background_prime(element):
        """Initial background priming pass.

        Fire-and-forget subactions whose overlays can be resolved from
        already-cached deps.  Defer everything else.
        """
        SpeculativeCachePrimingQueue._do_prime_pass(element)

    @staticmethod
    def _incremental_prime(element, dep):
        """Incremental priming after a dependency becomes cached.

        Re-attempt overlay resolution — the newly cached dep may unlock
        ARTIFACT overlays or ACTION overlays.
        """
        SpeculativeCachePrimingQueue._do_prime_pass(element)

    @staticmethod
    def _do_prime_pass(element):
        """Core priming logic shared by background and incremental passes.

        Iterates over all subactions, skipping already-submitted ones.
        For each remaining subaction, attempts to resolve all overlays.
        If resolvable, instantiates and submits fire-and-forget.
        """
        from ..._speculative_actions.instantiator import SpeculativeActionInstantiator
        from ..._protos.buildstream.v2 import speculative_actions_pb2

        context = element._get_context()
        cas = context.get_cascache()
        artifactcache = context.artifactcache

        weak_key = element._get_weak_cache_key()
        spec_actions = artifactcache.lookup_speculative_actions_by_weak_key(element, weak_key)
        if not spec_actions or not spec_actions.actions:
            return

        # Recover or initialize state
        submitted = getattr(element, "_SpeculativeCachePrimingQueue__priming_submitted", None) or set()
        action_outputs = getattr(element, "_SpeculativeCachePrimingQueue__priming_action_outputs", None) or {}
        adapted_digests = getattr(element, "_SpeculativeCachePrimingQueue__priming_adapted_digests", None) or {}

        # Pre-fetch CAS blobs only on first pass
        if not submitted:
            SpeculativeCachePrimingQueue._prefetch_cas_blobs(
                element, spec_actions, cas, artifactcache
            )

        # Build element lookup
        from ...types import _Scope

        dependencies = list(element._dependencies(_Scope.BUILD, recurse=True))
        element_lookup = {dep.name: dep for dep in dependencies}
        element_lookup[element.name] = element

        # Get services
        casd = context.get_casd()
        exec_service = casd.get_exec_service()
        if not exec_service:
            return

        ac_service = casd.get_ac_service()
        instantiator = SpeculativeActionInstantiator(cas, artifactcache, ac_service=ac_service)

        for spec_action in spec_actions.actions:
            base_hash = spec_action.base_action_digest.hash

            if base_hash in submitted:
                continue

            # Check overlay resolvability
            resolvable = True
            for overlay in spec_action.overlays:
                if overlay.type == speculative_actions_pb2.SpeculativeActions.Overlay.ACTION:
                    key = (overlay.source_action_digest.hash, overlay.source_path)
                    if key not in action_outputs and ac_service:
                        # The AC stores results under the adapted digest
                        # (what was actually executed), but overlays reference
                        # the base digest.  Look up with adapted, store under base.
                        base_key_hash = overlay.source_action_digest.hash
                        lookup_digest = adapted_digests.get(
                            base_key_hash,
                            overlay.source_action_digest,
                        )
                        SpeculativeCachePrimingQueue._fetch_action_outputs_keyed(
                            ac_service, lookup_digest, base_key_hash,
                            action_outputs,
                        )
                    if key not in action_outputs:
                        resolvable = False
                        break

            if not resolvable:
                continue

            try:
                action_digest = instantiator.instantiate_action(
                    spec_action, element, element_lookup,
                    action_outputs=action_outputs,
                )

                if not action_digest:
                    continue

                # Skip unchanged actions (already in AC from previous build)
                if action_digest.hash == base_hash:
                    submitted.add(base_hash)
                    continue

                SpeculativeCachePrimingQueue._submit_action_async(
                    exec_service, action_digest, element
                )
                element.info(
                    f"Submitted action {action_digest.hash[:8]} "
                    f"(base {base_hash[:8]})"
                )
                submitted.add(base_hash)
                adapted_digests[base_hash] = action_digest

            except Exception as e:
                element.warn(f"Failed to prime action: {e}")
                continue

        # Store state for next pass
        element.__priming_submitted = submitted
        element.__priming_action_outputs = action_outputs
        element.__priming_adapted_digests = adapted_digests

    # -----------------------------------------------------------------
    # Final priming pass (runs as a job when element becomes READY)
    # -----------------------------------------------------------------

    @staticmethod
    def _final_prime_pass(element):
        """Final priming pass when element is buildable.

        All deps are built, so all ActionResults are in AC.
        Resolve any remaining ACTION overlays and submit.
        """
        # Run the same logic — it will pick up where background left off
        SpeculativeCachePrimingQueue._do_prime_pass(element)

        # Count results
        submitted = getattr(element, "_SpeculativeCachePrimingQueue__priming_submitted", None) or set()

        from ..._protos.buildstream.v2 import speculative_actions_pb2

        context = element._get_context()
        artifactcache = context.artifactcache
        weak_key = element._get_weak_cache_key()
        spec_actions = artifactcache.lookup_speculative_actions_by_weak_key(element, weak_key)
        if not spec_actions:
            return (0, 0, 0)

        total = len(spec_actions.actions)
        primed = len(submitted)
        skipped = total - primed

        return (primed, skipped, total)

    # -----------------------------------------------------------------
    # Utility methods
    # -----------------------------------------------------------------

    @staticmethod
    def _prefetch_cas_blobs(element, spec_actions, cas, artifactcache):
        """Pre-fetch all CAS blobs needed for instantiation."""
        project = element._get_project()
        _, storage_remotes = artifactcache.get_remotes(project.name, False)
        remote = storage_remotes[0] if storage_remotes else None

        if not remote:
            return

        base_action_digests = [
            sa.base_action_digest
            for sa in spec_actions.actions
            if sa.base_action_digest.hash
        ]
        if base_action_digests:
            try:
                cas.fetch_blobs(remote, base_action_digests, allow_partial=True)
            except Exception:
                pass

        for digest in base_action_digests:
            try:
                action = cas.fetch_action(digest)
                if action and action.HasField("input_root_digest"):
                    cas.fetch_directory(remote, action.input_root_digest)
            except Exception:
                pass

    @staticmethod
    def _fetch_action_outputs(ac_service, action_digest, action_outputs):
        """Fetch ActionResult from action cache and record output file digests."""
        SpeculativeCachePrimingQueue._fetch_action_outputs_keyed(
            ac_service, action_digest, action_digest.hash, action_outputs
        )

    @staticmethod
    def _fetch_action_outputs_keyed(ac_service, action_digest, key_hash, action_outputs):
        """Fetch ActionResult and store outputs keyed by a specified hash.

        When resolving ACTION overlays, the overlay references the base
        action digest but the AC stores the result under the adapted
        digest.  This method allows looking up with one digest but
        storing results under a different key hash.
        """
        try:
            from ..._protos.build.bazel.remote.execution.v2 import remote_execution_pb2

            request = remote_execution_pb2.GetActionResultRequest(
                action_digest=action_digest,
            )
            action_result = ac_service.GetActionResult(request)
            if action_result:
                for output_file in action_result.output_files:
                    action_outputs[(key_hash, output_file.path)] = output_file.digest
        except Exception:
            pass

    @staticmethod
    def _submit_action_async(exec_service, action_digest, element):
        """Submit an Execute request fire-and-forget style.

        Reads the first response from the stream to confirm the action
        was accepted by casd, then returns.  The action continues
        executing asynchronously in casd and its result will appear in
        the action cache when complete.
        """
        try:
            from ..._protos.build.bazel.remote.execution.v2 import remote_execution_pb2

            request = remote_execution_pb2.ExecuteRequest(
                action_digest=action_digest,
                skip_cache_lookup=False,
            )

            # Read first response to confirm acceptance, then drop the stream
            stream = exec_service.Execute(request)
            next(stream, None)

        except Exception as e:
            element.warn(f"Failed to submit priming action: {e}")
