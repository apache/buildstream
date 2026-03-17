..
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.


.. _speculative_actions:

Speculative Actions
===================

Speculative actions speed up rebuilds by pre-populating the action cache
with adapted versions of previously recorded build actions. When a dependency
changes, the individual compile and link commands from the previous build
are adapted with updated input digests and executed ahead of the actual
build, so that by the time recc runs the same commands, they hit the
action cache instead of being executed from scratch.


Overview
--------

A typical rebuild scenario: a developer modifies a leaf library. Every
downstream element needs rebuilding because its dependency changed. But
the downstream elements' own source code hasn't changed — only the
dependency artifacts are different. Speculative actions exploit this by:

1. **Recording** subactions from the previous build (via recc through
   the ``remote-apis-socket``)
2. **Generating** overlays that describe how each subaction's input files
   relate to source elements and dependency artifacts
3. **Storing** the speculative actions on the artifact proto, keyed by
   the element's weak cache key (stable across dependency version changes)
4. **Priming** the action cache on the next build by instantiating the
   stored actions with current dependency digests and executing them


Subaction Recording
-------------------

When an element builds with ``remote-apis-socket`` configured and
``CC: recc gcc`` as the compiler, each compiler invocation goes through
recc, which sends an ``Execute`` request to buildbox-casd's nested
server via the socket. buildbox-casd records each action digest as a
subaction. When the sandbox's ``StageTree`` session ends, the subaction
digests are returned in the ``StageTreeResponse`` and added to the
parent ``ActionResult.subactions`` field.

BuildStream reads ``action_result.subactions`` after each sandbox
command execution (``SandboxREAPI._run()``) and accumulates them on
the sandbox object. After a successful build, ``Element._assemble()``
transfers them to the element via ``_set_subaction_digests()``.


Overlay Generation
------------------

The ``SpeculativeActionsGenerator`` runs after the build queue. For each
element with subaction digests:

1. Builds a **digest cache** mapping file content hashes to their origin:

   - **SOURCE** overlays: files from the element's own source tree
   - **ARTIFACT** overlays: files from dependency artifacts
   - SOURCE takes priority over ARTIFACT when the same digest appears
     in both

2. For each subaction, fetches the ``Action`` proto and traverses its
   input tree to find all file digests. Each digest that matches the
   cache produces an ``Overlay`` recording:

   - The overlay type (SOURCE, ARTIFACT, or ACTION)
   - The source element name (or producing action's base digest hash
     for ACTION overlays)
   - The file path within the source/artifact tree
   - The target digest to replace

3. Generates **ACTION overlays** for inter-subaction dependencies, both
   within the element and across dependency elements:

   - **Intra-element**: subactions are processed in order; after each,
     the generator fetches its ``ActionResult`` to learn what it produced.
     Later subactions whose input digests match get ACTION overlays
     (e.g., link's ``main.o`` linked to the compile that produced it).
   - **Cross-element**: for each dependency with stored ``SpeculativeActions``,
     the generator fetches ActionResults of the dependency's subactions
     and seeds the output map.  If the current element's subaction input
     contains an intermediate file produced by a dependency's subaction
     (not in the artifact — those are ARTIFACT overlays), a cross-element
     ACTION overlay is created with ``source_element`` set to the
     dependency name.

4. Stores the ``SpeculativeActions`` proto on the artifact, which is
   saved under both the strong and weak cache keys.


Weak Key Lookup
---------------

The weak cache key includes everything about the element itself (sources,
environment, build commands, sandbox config) but only dependency **names**
(not their cache keys). This means:

- When a dependency is rebuilt with new content, the downstream element's
  weak key remains **stable**
- The speculative actions stored under the weak key from the previous
  build are still **reachable**
- When the element's own sources or configuration change, the weak key
  changes, correctly **invalidating** stale speculative actions


Overlay Fallback Resolution
~~~~~~~~~~~~~~~~~~~~~~~~~~~

When the same file digest appears in both a dependency's source tree
and its artifact (e.g. a header file), both SOURCE and ARTIFACT
overlays are generated. At instantiation time, they are tried in
priority order: SOURCE first, then ARTIFACT, then ACTION.

This enables parallelism: if a dependency is rebuilding, its SOURCE
overlay can resolve as soon as the dependency's sources are fetched
(before its full build completes), while the ARTIFACT overlay serves
as a fallback if the sources are not available (dependency not
rebuilding this invocation — its artifact is already cached).

Overlay data availability at priming time:

- If a referenced element is **not rebuilding**: its sources/artifacts
  haven't changed, so the overlay's target digest remains valid and
  ARTIFACT resolution succeeds from the cached artifact.
- If a referenced element **is rebuilding**: its old artifact is
  invalidated (new strong key), so ARTIFACT resolution returns None.
  SOURCE resolution may succeed if the Fetch queue has already run.
  If neither resolves, the subaction is deferred until the dependency
  completes.


Action Instantiation
--------------------

The ``SpeculativeActionInstantiator`` adapts stored actions for the
current dependency versions:

1. Fetches the base action from CAS
2. Resolves each overlay with fallback (first resolved wins per target
   digest):

   - **SOURCE** overlays: finds the current file digest in the element's
     source tree by path
   - **ARTIFACT** overlays: finds the current file digest in the
     dependency's artifact tree by path
   - **ACTION** overlays: finds the current output file digest from the
     producing subaction's ``ActionResult`` by path — looked up in
     ``action_outputs`` (intra-element) or via the action cache
     (cross-element)

3. Builds a digest replacement map (old hash → new digest)
4. Recursively traverses the action's input tree, replacing file digests
5. Stores the modified action in CAS
6. If no digests changed, returns the base action digest (already cached)


Pipeline Integration
--------------------

The scheduler queue order with speculative actions enabled::

    Pull → Fetch → Priming → Build → Generation → Push

**Pull Queue**: For elements not cached by strong key, also pulls the
weak key artifact proto from remotes. This is a lightweight pull — just
the metadata, not the full artifact files.

**Priming Queue** (``SpeculativeCachePrimingQueue``): Runs before the
build queue. Uses the PENDING state to hold elements while their
dependencies build, running background priming concurrently.

Elements without stored SpeculativeActions skip this queue entirely.
Elements that are already buildable (all deps cached) get a single
priming pass as a job. Elements with unbuilt dependencies enter as
PENDING:

1. ``register_pending_element``: sets a per-dep callback
   (``_set_build_dep_cached_callback``) and launches background
   priming in the scheduler's thread pool
2. **Background priming**: pre-fetches CAS blobs, instantiates
   subactions whose overlays are resolvable from already-cached deps,
   submits them fire-and-forget (reads first stream response to
   confirm acceptance, then drops the stream)
3. **Per-dep callback**: as each dependency becomes cached, the
   callback triggers incremental priming — newly resolvable ARTIFACT
   and ACTION overlays are resolved and submitted
4. **Final pass** (element becomes buildable): all dependencies are
   built, all ``ActionResults`` are in the action cache. Remaining
   ACTION overlays are resolved using adapted digests from earlier
   submissions. Remaining subactions are submitted fire-and-forget.
5. Element proceeds to BuildQueue with all actions primed

Unchanged actions (instantiated digest equals base digest) skip
submission — they are already in the action cache from the previous
build.

**Build Queue**: Builds elements as usual. When recc runs a compile or
link command, it checks the action cache first. If priming succeeded,
the adapted action is already cached → **action cache hit**.

**Generation Queue** (``SpeculativeActionGenerationQueue``): Runs after
the build queue. Generates overlays from newly recorded subactions and
stores them for future priming.


Scaling Considerations
----------------------

Execute calls are full builds
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Each adapted action runs a full build command (e.g. ``gcc -c``) through
buildbox-run. For N elements with M subactions each, that's N×M Execute
calls competing for CPU with the actual build queue.

**Mitigation**: With remote execution, priming fans out across a cluster.
Locally, casd's ``--jobs`` flag limits concurrent executions.

FetchTree calls are sequential
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The pre-fetch phase does one ``FetchTree`` per base action. For an
element with many subactions, this is many sequential calls.

**Mitigation**: Batch ``FetchTree`` calls or parallelize them. Could
also collect all directory digests and issue a single
``FetchMissingBlobs``.

CAS storage growth
~~~~~~~~~~~~~~~~~~

Every adapted action produces new directory trees in CAS. Most content
is shared (CAS deduplication), but root directories and Action protos
are unique per adaptation. CAS quota management handles eviction.

Priming stale SA is wasteful
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If an element's build commands changed, its SA may produce adapted
actions that don't match what recc computes. The weak key includes
build configuration, so this only happens when the element itself
changed — in which case the SA is correctly invalidated.


Future Optimizations
--------------------

1. **Topological prioritization**: Prime elements in build order (leaves
   first) to maximize the chance priming completes before building starts.

2. **Selective priming**: Skip cheap actions (fast link steps), prioritize
   expensive ones (long compilations).

3. **Batch FetchTree**: Collect all input root digests and fetch in
   parallel or in a single batch.
