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

A typical rebuild scenario: a developer modifies a low-level library
(e.g. a base SDK element).  Every downstream element needs rebuilding
because its dependency changed.  But the downstream elements' own source
code hasn't changed — only the dependency artifacts are different.
Speculative actions exploit this by:

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
     dependency name.  Subsequently, a copy of the SpeculativeAction that is referenced by the ACTION overlay, is added to the list of speculative actions with its element field set to its originating element.  We then evaluate that SA in the same way and copy in further SA's as needed, setting element to the dependency if it isn't set.  We only need to walk the list of SAs of the dependency, which by definition is complete.  This approach makes the SA list self-sufficient, at the cost of some duplication. 

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
priority order: **SOURCE first, then ACTION, then ARTIFACT**.

- **SOURCE** overlays enable the earliest resolution — as soon as
  the element's sources are fetched, before any build completes.
- **ACTION** overlays resolve intermediate files (e.g. ``.o`` files)
  that are produced by prior subactions but not present in artifacts.
  They are tried before ARTIFACT because they provide a more direct
  resolution path for intermediate files.
- **ARTIFACT** overlays serve as a fallback when sources are not
  available (dependency not rebuilding this invocation — its artifact
  is already cached).

Overlay data availability at priming time:

- If a referenced element is **not rebuilding**: its sources/artifacts
  haven't changed, so the overlay's target digest remains valid and
  ARTIFACT resolution succeeds from the cached artifact.
- If a referenced element **is rebuilding**: its old artifact is
  invalidated (new strong key), so ARTIFACT resolution returns None.
  SOURCE resolution may succeed if the Fetch queue has already run.
  If neither resolves, the subaction is deferred until the dependency's
  sources become available or its artifact is cached.


Action Instantiation
--------------------

The ``SpeculativeActionInstantiator`` adapts stored actions for the
current dependency versions:

0. **Already-instantiated check**: if the base action's hash is found
   in the global ``instantiated_actions`` dict, returns the previously
   adapted digest immediately (avoids redundant work when multiple
   elements reference the same dependency subaction)
1. Fetches the base action from CAS
2. Resolves each overlay with fallback (first resolved wins per target
   digest), in priority order **SOURCE > ACTION > ARTIFACT**:

   - **SOURCE** overlays: finds the current file digest in the element's
     source tree by path
   - **ACTION** overlays: looks up the producing subaction's adapted
     digest in the global ``instantiated_actions`` dict, then fetches
     the ``ActionResult`` from the action cache to find the output
     file's current digest.  If the producing action was never
     instantiated, the overlay is dropped gracefully.
   - **ARTIFACT** overlays: finds the current file digest in the
     dependency's artifact tree by path

3. Builds a digest replacement map (old hash → new digest), skipping
   when old hash == new digest.  If the replacement map is empty, the
   SA is marked as done.
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
   confirm acceptance, then drops the stream).  Each instantiated
   action is recorded in the global ``instantiated_actions`` dict.
3. **Per-dep callback**: as each dependency becomes cached, the
   callback triggers incremental priming — newly resolvable ARTIFACT
   and ACTION overlays are resolved and submitted
4. **Final pass** (element becomes buildable): all dependencies are
   built, all ``ActionResults`` are in the action cache. Remaining
   ACTION overlays are resolved via the global ``instantiated_actions``
   dict. Remaining subactions are submitted fire-and-forget.
5. Element proceeds to BuildQueue with all actions primed

Unchanged actions (instantiated digest equals base digest) skip
submission — they are already in the action cache from the previous
build.

**Global instantiated_actions**: A shared dict
(``base_action_hash → adapted_action_digest``) accessible to all
elements during priming.  When element A instantiates a subaction,
the mapping is immediately visible to element B's priming.  This
enables cross-element ACTION overlay resolution — element B can look
up element A's adapted subaction digest to find intermediate files
(e.g. generated headers) that aren't in artifacts.  The dict is
protected by a threading lock for write access; reads are safe under
the GIL.

**Build Queue**: Builds elements as usual. When recc runs a compile or
link command, it checks the action cache first. If priming succeeded,
the adapted action is already cached → **action cache hit**.

**Generation Queue** (``SpeculativeActionGenerationQueue``): Runs after
the build queue. Generates overlays from newly recorded subactions and
stores them for future priming.


Example Scenarios
-----------------

The following scenarios illustrate how speculative actions behave across
different dependency change patterns.  In each case, "unchanged" means
the element's own sources did not change (its weak key is stable), so
its stored SA is available for priming.


Single dependency change
~~~~~~~~~~~~~~~~~~~~~~~~

::

    base (sources CHANGED) → liba (unchanged) → app (unchanged)

The most common CI scenario: a low-level element is modified, all
downstream elements need rebuilding.

- **base**: weak key changed → no SA available → builds from scratch.
- **liba**: weak key unchanged → SA available.

  - SOURCE overlays (liba's own ``.c`` files): resolve immediately.
  - ARTIFACT overlays (base's headers): deferred until base builds.
  - When base finishes → per-dep callback fires → ARTIFACT overlays
    resolve → liba's compile actions are submitted fire-and-forget.
  - ACTION overlays (intra-element, e.g. ``ar`` consuming ``.o`` files
    from compile): resolve sequentially from ``instantiated_actions``
    once the compile actions complete.

- **app**: same pattern — waits for liba, then resolves and submits.

Result: every downstream element gets full cache hits on all subactions.


Cross-element intermediate files
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

::

    codegen (unchanged) → liba (unchanged)
         |                    |
         generates gen.h      compiles with gen.h

codegen's build produces ``gen.h`` as a subaction output.  liba's
compile subaction uses ``gen.h`` as an input, tracked by a cross-element
ACTION overlay.

- **codegen**: weak key unchanged → SA available → primed.  Its compile
  action is recorded in ``instantiated_actions``.
- **liba**: ACTION overlay for ``gen.h`` looks up codegen's subaction
  in ``instantiated_actions`` → found → fetches ``ActionResult`` from
  AC → resolves ``gen.h``'s adapted digest → submitted.

Result: the global ``instantiated_actions`` dict enables cross-element
resolution of intermediate files.  Without the global dict (per-element
state only), liba would not see codegen's adapted digest.


Intra-element action chains (compile → archive)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

::

    base (sources CHANGED) → liba (unchanged)
                                  compile: base.h + liba.c → liba.o
                                  archive: ar rcs libliba.a liba.o

liba's archive action depends on ``.o`` files produced by liba's own
compile actions.  These ``.o`` files are intermediate — they are not
installed in artifacts.

- **liba**: priming processes subactions in order.

  1. Compile action: ARTIFACT overlay for ``base.h`` deferred until
     base builds.  When base finishes → resolves → submitted →
     recorded in ``instantiated_actions``.
  2. Archive action: ACTION overlay for ``liba.o`` looks up compile's
     hash in ``instantiated_actions`` → found → fetches
     ``ActionResult`` → resolves ``liba.o`` → submitted.

Result: the full compile → archive chain fires as soon as base completes.
Downstream elements that depend on ``libliba.a`` via ARTIFACT overlays
resolve once liba's artifact is cached.


Changed element breaks the action chain
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

::

    codegen (sources CHANGED) → liba (unchanged) → app (unchanged)
         |                           |
         generates gen.h             compiles with gen.h

When codegen's sources change, its weak key changes, so its SA is
unavailable and codegen builds from scratch.  Its subactions are never
primed and do not appear in ``instantiated_actions``.

- **liba**: ACTION overlay for ``gen.h`` references codegen's subaction
  → ``instantiated_actions.get(...)`` returns None → **overlay dropped**.
  If ``gen.h`` is also installed in codegen's artifact, an ARTIFACT
  overlay exists as fallback → resolves once codegen finishes building.
  If ``gen.h`` is truly intermediate (not in the artifact), that
  specific compile action cannot be adapted and falls back to full
  execution during liba's build.

- **liba finishes priming**: its adapted actions are recorded in
  ``instantiated_actions``.  From this point, all downstream elements
  (app, etc.) can resolve ACTION overlays referencing liba's subactions.

Result: one level of delay (codegen must build before the chain
resumes), but the chain propagates from liba onward.  See
:ref:`referenced_speculative_actions` for a future optimization that
would eliminate this delay.


Multiple source changes in a chain
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

::

    base (sources CHANGED) → liba (sources CHANGED) → app (unchanged)

Both base and liba have changed sources, so both have changed weak keys
and no SAs available.  Both build from scratch.

- **app**: weak key unchanged → SA available.

  - ARTIFACT overlays for liba: deferred until liba builds → resolve.
  - ACTION overlays for liba's subactions: liba was never primed →
    ``instantiated_actions`` has no entries for liba's subactions →
    **overlays dropped**.  App's compile actions that depend on liba's
    intermediate files (e.g. ``.o`` files not in the artifact) cannot
    be adapted.

Result: app gets cache hits for subactions that only depend on
artifacts (the common case), but misses on subactions that depend on
intermediate files from liba.  This is a graceful degradation — those
subactions execute normally during app's build.


Dependency adapted but sources unchanged
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

::

    base (deps CHANGED, not sources) → liba (unchanged) → app (unchanged)

base's own sources didn't change (weak key stable), but one of base's
dependencies changed, so base has a different strong key.

- **base**: weak key unchanged → SA available → primed.  Adapted
  actions recorded in ``instantiated_actions``.
- **liba**: ACTION overlays for base's subactions → found in
  ``instantiated_actions`` (populated by base's priming) → resolve.
- **app**: similarly resolves via ``instantiated_actions``.

Result: the global dict ensures that base's adapted digests propagate
to all downstream elements, even though base's artifact hasn't changed
content-wise.  Without the global dict, liba would fail to look up
base's adapted digests.



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


.. _referenced_speculative_actions:

Future Optimizations
--------------------

1. **ReferencedSpeculativeActions**: Store
   ``repeated ReferencedSpeculativeActions`` on the SA proto — pointers
   (``element_name``, ``sa_digest``) to dependency elements' SAs.  This
   enables a downstream element to instantiate a dependency's SA even
   when the dependency's weak key changed (its sources changed).

   Consider this scenario::

       codegen (sources CHANGED) → liba (unchanged)
            |                           |
            generates gen.h             compiles with gen.h

   Currently, codegen's weak key changes, so its SA is unavailable.
   liba's ACTION overlay for ``gen.h`` is dropped because codegen was
   never primed and ``instantiated_actions`` has no entry for codegen's
   subaction.  liba must wait for codegen to build before the ARTIFACT
   fallback (if ``gen.h`` is installed) or full execution (if ``gen.h``
   is truly intermediate) can proceed.

   With ReferencedSAs, liba's artifact would store a reference to
   codegen's SA from the previous build.  During priming, liba could
   retrieve codegen's SA, instantiate codegen's subactions (adapting
   them with codegen's new sources), and populate
   ``instantiated_actions`` with codegen's adapted digests.  The ACTION
   overlay for ``gen.h`` would then resolve immediately, eliminating
   the one-level delay.

   The benefit is most pronounced when a low-level element with
   generated intermediate files (headers, protocol buffer outputs,
   code-generated sources) changes frequently and has many downstream
   dependents.  The cost is additional complexity in SA storage and
   retrieval, plus the overhead of instantiating dependency SAs during
   priming.  Whether this trade-off is worthwhile depends on real-world
   profiling of rebuild patterns.

2. **Topological prioritization**: Prime elements in build order
   (dependencies first) to maximize the chance priming completes before
   building starts.

3. **Selective priming**: Skip cheap actions (fast link steps), prioritize
   expensive ones (long compilations).  Only skip when it doesn't break
   SA chains.

4. **Batch FetchTree**: Collect all input root digests and fetch in
   parallel or in a single batch.

5. **Storage**: Store SAs more efficiently so that they can be pulled
   down efficiently.

6. **Generation**: Find a way to make the output tree to input tree
   matching more efficient.
