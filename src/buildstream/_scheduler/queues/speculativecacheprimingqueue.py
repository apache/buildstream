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

Cross-element ACTION overlay resolution uses a global
``_instantiated_actions`` dict (base_action_hash → adapted_action_digest)
shared across all elements.  When element A's priming instantiates a
subaction, the mapping is immediately visible to element B's priming,
enabling cross-element intermediate file resolution.
"""

import threading

# Local imports
from . import Queue, QueueStatus
from ..jobs import JobStatus
from ..resources import ResourceType


class SpeculativeCachePrimingQueue(Queue):

    action_name = "Priming cache"
    complete_name = "Cache primed"
    resources = [ResourceType.UPLOAD]

    # Global shared state: maps base_action_hash -> adapted_action_digest
    # Populated by all elements during priming, enabling cross-element
    # ACTION overlay resolution.
    _instantiated_actions = {}
    _instantiated_actions_lock = threading.Lock()

    # Elements whose priming has completed (all passes done).
    # Used to determine if an ACTION overlay's producing element has
    # finished priming — if so and the action isn't in _instantiated_actions,
    # the overlay can be permanently dropped from the SA proto.
    _primed_elements = set()

    def get_process_func(self):
        # Runs when element is READY (buildable) — final priming pass
        return SpeculativeCachePrimingQueue._final_prime_pass

    def status(self, element):
        if element._cached():
            # Already cached — no priming needed.  Record as primed so
            # downstream elements know this element's actions won't appear
            # in _instantiated_actions.
            SpeculativeCachePrimingQueue._primed_elements.add(element.name)
            return QueueStatus.SKIP

        weak_key = element._get_weak_cache_key()
        if not weak_key:
            SpeculativeCachePrimingQueue._primed_elements.add(element.name)
            return QueueStatus.SKIP

        context = element._get_context()
        artifactcache = context.artifactcache
        spec_actions = artifactcache.lookup_speculative_actions_by_weak_key(element, weak_key)
        if not spec_actions or not spec_actions.actions:
            SpeculativeCachePrimingQueue._primed_elements.add(element.name)
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

        # Register per-dep callback for when a dependency finishes
        # priming — its adapted actions are now in _instantiated_actions
        # and downstream elements can resolve cross-element ACTION overlays
        element._set_build_dep_primed_callback(self._on_dep_primed)

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

    def _on_dep_primed(self, element, dep):
        """Called each time a build dependency finishes priming.

        The dep's adapted action digests are now in _instantiated_actions.
        Launches incremental priming to resolve cross-element ACTION
        overlays that reference the dep's subactions.
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

        # Record element as primed so other elements can determine
        # whether ACTION overlay producers have finished.
        with SpeculativeCachePrimingQueue._instantiated_actions_lock:
            SpeculativeCachePrimingQueue._primed_elements.add(element.name)

        # Notify reverse build deps that this element finished priming —
        # its adapted actions are now in _instantiated_actions and
        # downstream elements can resolve cross-element ACTION overlays.
        element._notify_build_deps_primed()

        # Clear priming state and per-dep callbacks
        element._set_build_dep_cached_callback(None)
        element._set_build_dep_primed_callback(None)
        element.__priming_submitted = None
        element.__priming_spec_actions = None
        element.__priming_resolved = None
        element.__priming_ac_cache = None

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

        ACTION overlay resolution uses the global _instantiated_actions
        dict.  For each ACTION overlay:
        - If the producing action is in _instantiated_actions → check
          AC for the ActionResult; if not yet available, defer the SA
        - If the producing action is NOT in _instantiated_actions AND
          its source_element has finished priming → the producing
          action will never appear; remove the overlay from the proto
        - If the producing action is NOT in _instantiated_actions AND
          its source_element has NOT finished priming → skip for now,
          it may appear on a later pass

        Dropped overlays are removed directly from the in-memory SA
        proto (which is discarded after the build).
        """
        from ..._speculative_actions.instantiator import SpeculativeActionInstantiator
        from ..._protos.buildstream.v2 import speculative_actions_pb2
        from ..._protos.build.bazel.remote.execution.v2 import remote_execution_pb2

        context = element._get_context()
        cas = context.get_cascache()
        artifactcache = context.artifactcache

        # Use the cached spec_actions proto if available (mutations and
        # _resolved_cache attributes must survive across passes).  Only
        # deserialize from CAS on the first pass.
        spec_actions = getattr(element, "_SpeculativeCachePrimingQueue__priming_spec_actions", None)
        if spec_actions is None:
            weak_key = element._get_weak_cache_key()
            spec_actions = artifactcache.lookup_speculative_actions_by_weak_key(element, weak_key)
            if not spec_actions or not spec_actions.actions:
                return

        # Recover or initialize per-element state
        submitted = getattr(element, "_SpeculativeCachePrimingQueue__priming_submitted", None) or set()
        # Per-SA resolution caches: {base_action_hash -> {target_hash -> new_digest}}
        resolved_caches = getattr(element, "_SpeculativeCachePrimingQueue__priming_resolved", None) or {}
        # AC result cache: avoids redundant GetActionResult gRPCs across passes.
        # Maps adapted_digest_hash -> ActionResult (or False for "checked, not found").
        ac_cache = getattr(element, "_SpeculativeCachePrimingQueue__priming_ac_cache", None) or {}

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

        # References to global state (reads are GIL-safe)
        instantiated_actions = SpeculativeCachePrimingQueue._instantiated_actions
        primed_elements = SpeculativeCachePrimingQueue._primed_elements

        for spec_action in spec_actions.actions:
            base_hash = spec_action.base_action_digest.hash

            if base_hash in submitted:
                continue

            # Check ACTION overlay resolvability against global state,
            # removing overlays that will never resolve.
            resolvable = True
            to_remove = []
            for i, overlay in enumerate(spec_action.overlays):
                if overlay.type != speculative_actions_pb2.SpeculativeActions.Overlay.ACTION:
                    continue

                source_hash = overlay.source_action_digest.hash
                adapted = instantiated_actions.get(source_hash)

                if adapted is not None:
                    # Producing action was instantiated — check if
                    # result is in AC (using cache to avoid redundant
                    # gRPC calls across passes)
                    cached_result = ac_cache.get(adapted.hash)
                    if cached_result is None:
                        # Not in cache — query AC
                        if ac_service:
                            try:
                                request = remote_execution_pb2.GetActionResultRequest(
                                    action_digest=adapted,
                                )
                                action_result = ac_service.GetActionResult(request)
                                if action_result:
                                    ac_cache[adapted.hash] = action_result
                                else:
                                    # Not yet complete — defer (don't cache
                                    # negative result, it may complete later)
                                    resolvable = False
                                    break
                            except Exception:
                                resolvable = False
                                break
                    elif cached_result is False:
                        # Previously checked and not found
                        resolvable = False
                        break
                    # else: cached_result is a valid ActionResult, proceed
                else:
                    # Not in instantiated_actions — check if the
                    # producing element has finished priming
                    source_elem = overlay.source_element or element.name
                    if source_elem in primed_elements:
                        # Element finished priming without instantiating
                        # this action — it will never appear.  Mark for
                        # removal from the proto.
                        to_remove.append(i)
                    # else: source element not yet primed, skip for now

            # Remove dropped overlays from the proto (reverse order to
            # preserve indices)
            for i in reversed(to_remove):
                del spec_action.overlays[i]

            if not resolvable:
                continue

            try:
                # Get or create per-SA resolution cache
                sa_cache = resolved_caches.setdefault(base_hash, {})
                action_digest = instantiator.instantiate_action(
                    spec_action, element, element_lookup,
                    instantiated_actions=instantiated_actions,
                    resolved_cache=sa_cache,
                )

                if not action_digest:
                    continue

                # Record in global state (write-locked)
                with SpeculativeCachePrimingQueue._instantiated_actions_lock:
                    instantiated_actions[base_hash] = action_digest

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

            except Exception as e:
                element.warn(f"Failed to prime action: {e}")
                continue

        # Store per-element state for next pass
        element.__priming_submitted = submitted
        element.__priming_spec_actions = spec_actions
        element.__priming_resolved = resolved_caches
        element.__priming_ac_cache = ac_cache

    # -----------------------------------------------------------------
    # Final priming pass (runs as a job when element becomes READY)
    # -----------------------------------------------------------------

    @staticmethod
    def _final_prime_pass(element):
        """Final priming pass when element is buildable.

        All deps are built, so all ActionResults are in AC.
        Resolve any remaining ACTION overlays and submit.
        """
        # Run the same logic — it will pick up where background left off.
        # By now all deps are built, so _primed_elements contains all
        # producing elements.  Any ACTION overlay whose source_element
        # is in _primed_elements but whose action is not in
        # _instantiated_actions will be removed from the proto.
        SpeculativeCachePrimingQueue._do_prime_pass(element)

        # Count results
        submitted = getattr(element, "_SpeculativeCachePrimingQueue__priming_submitted", None) or set()
        spec_actions = getattr(element, "_SpeculativeCachePrimingQueue__priming_spec_actions", None)
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
        """Pre-fetch all CAS blobs needed for instantiation.

        Fetches base action blobs in a single batch, then deduplicates
        input root digests and fetches directory trees concurrently.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

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

        # Collect and deduplicate input root digests
        unique_roots = {}  # hash -> digest
        for digest in base_action_digests:
            try:
                action = cas.fetch_action(digest)
                if action and action.HasField("input_root_digest"):
                    root = action.input_root_digest
                    if root.hash not in unique_roots:
                        unique_roots[root.hash] = root
            except Exception:
                pass

        if not unique_roots:
            return

        # Fetch directory trees concurrently
        def _fetch_tree(root_digest):
            try:
                cas.fetch_directory(remote, root_digest)
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=min(16, len(unique_roots))) as pool:
            futures = [pool.submit(_fetch_tree, d) for d in unique_roots.values()]
            for f in as_completed(futures):
                pass  # Errors handled inside _fetch_tree

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
