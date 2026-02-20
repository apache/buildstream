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


.. _cachekeys:


Cache keys
==========

Cache keys for artifacts are generated from the inputs of the build process
for the purpose of reusing artifacts in a well-defined, predictable way.

Structure
---------
Cache keys are SHA256 hash values generated from a UTF-8 JSON document that
includes:

* Environment (e.g., project configuration and variables).
* Element configuration (details depend on element kind, ``Element.get_unique_key()``).
* Sources (``Source.get_unique_key()``).
* Dependencies (depending on cache key type, see below).
* Public data.

Cache key types
---------------
There are two types of cache keys in BuildStream, ``strong`` and ``weak``.

The purpose of a ``strong`` cache key is to capture the state of as many aspects
as possible that can have an influence on the build output. The aim is that
builds will be fully reproducible as long as the cache key doesn't change,
with suitable module build systems that don't embed timestamps, for example.

A ``strong`` cache key includes the strong cache key of each build dependency
(and their runtime dependencies) of the element as changes in build dependencies
(or their runtime dependencies) can result in build differences in reverse
dependencies. This means that whenever the strong cache key of a dependency
changes, the strong cache key of its reverse dependencies will change as well.

A ``weak`` cache key has an almost identical structure, however, it includes
only the names of build dependencies, not their cache keys or their runtime
dependencies. A weak cache key will thus still change when the element itself
or the environment changes but it will not change when a dependency is updated.

For elements without build dependencies the ``strong`` cache key is identical
to the ``weak`` cache key.

Note that dependencies which are not required at build time do not affect
either kind of key.

Strict build plan
-----------------
This is the default build plan that exclusively uses ``strong`` cache keys
for the core functionality. An element's cache key can be calculated when
the cache keys of the element's build dependencies (and their runtime
dependencies) have been calculated and either tracking is not enabled or it
has already completed for this element, i.e., the ``ref`` is available.
This means that with tracking disabled the cache keys of all elements could be
calculated right at the start of a build session.

While BuildStream only uses ``strong`` cache keys with the strict build plan
for the actual staging and build process, it will still calculate ``weak``
cache keys for each element. This allows BuildStream to store the artifact
in the cache with both keys, reducing rebuilds when switching between strict
and non-strict build plans. If the artifact cache already contains an
artifact with the same ``weak`` cache key, it's replaced. Thus, non-strict
builds always use the latest artifact available for a given ``weak`` cache key.

Non-strict build plan
---------------------
The non-strict build plan disables the time-consuming automatic rebuild of
reverse dependencies at the cost of dropping the reproducibility benefits.
It uses the ``weak`` cache keys for the core staging and build process.
I.e., if an artifact is available with the calculated ``weak`` cache key,
it will be reused for staging instead of being rebuilt. ``weak`` cache keys
can be calculated early in the build session. After tracking, similar to
when ``strong`` cache keys can be calculated with a strict build plan.

Similar to how strict build plans also calculate ``weak`` cache keys, non-strict
build plans also calculate ``strong`` cache keys. However, this is slightly
more complex. To calculate the ``strong`` cache key of an element, BuildStream
requires the ``strong`` cache keys of the build dependencies (and their runtime
dependencies).

The build dependencies of an element may have been updated since the artifact
was built. With the non-strict build plan the artifact will still be reused.
However, this means that we cannot use a ``strong`` cache key calculated purely
based on the element definitions. We need a cache key that matches the
environment at the time the artifact was built, not the current definitions.

The only way to get the correct ``strong`` cache key is by retrieving it from
the metadata stored in the artifact. As artifacts may need to be pulled from a
remote artifact cache, the ``strong`` cache key is not readily available early
in the build session. However, it can always be retrieved when an element is
about to be built, as the dependencies are guaranteed to be in the local
artifact cache at that point.

``Element._get_cache_key_from_artifact()`` extracts the ``strong`` cache key
from an artifact in the local cache. ``Element._get_cache_key_for_build()``
calculates the ``strong`` cache key that is used for a particular build job.
This is used for the embedded metadata and also as key to store the artifact in
the cache.
