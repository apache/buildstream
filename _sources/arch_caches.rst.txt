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


.. _caches:


Caches
======

BuildStream uses local caches to avoid repeating work, and can have remote
caches configured to allow the results of work to be shared between multiple
users. There are caches for both elements and sources that map keys to relevant
metadata and point to data in CAS.

Content Addressable Storage (CAS)
---------------------------------

The majority of data is stored in Content Addressable Storage or CAS, which
indexes stored files by the SHA256 hash of their contents. This allows for a
flat file structure as well as any repeated data to be shared across a CAS. In
order to store directory structures BuildStream's CAS uses `protocol buffers`_
for storing directory and file information as defined in Google's `REAPI`_.

The data itself is stored in CAS which is defined by the `remote execution protocol`_,
and BuildStream also uses the `remote asset protocol`_ in order to address stored
content using symbolic labels, such as :ref:`artifact names <artifact_names>` for
artifacts.


Artifact caches
---------------

Artifacts store build results of an element which is then referred to by its
cache key (described in :ref:`cachekeys`). The artifacts information is then
stored in a protocol buffer, defined in ``artifact.proto``, which includes
metadata such as the digest of the files root; strong and weak keys; and log
files digests. The digests point to locations in the CAS of relavant files and
directories, allowing BuildStream to query remote CAS servers for this
information.

Source caches
-------------

Sources are cached by running the :mod:`Source.stage
<buildstream.source.Source.stage>` method and capturing the directory output of
this into the CAS, which then use the sources key to refer to this. The source
key will be calculated with the plugins defined :mod:`Plugin.get_unique_key
<buildstream.plugin.Plugin.get_unique_key>` and, depending on whether the source
requires previous sources to be staged (e.g. the patch plugin), the unique key
of all sources listed before it in an element. Source caches are simpler than
artifacts, as they just need to map a source key to a directory digest, with no
additional metadata.

.. note::

   Not all plugins use the same result as the staged output for workspaces. As a
   result when initialising a workspace, BuildStream may require fetching the
   original source if it only has the source in the source cache.

.. _protocol buffers: https://developers.google.com/protocol-buffers/docs/overview
.. _grpc: https://grpc.io
.. _REAPI: https://github.com/bazelbuild/remote-apis
.. _remote execution protocol: https://github.com/bazelbuild/remote-apis/blob/main/build/bazel/remote/execution/v2/remote_execution.proto
.. _remote asset protocol: https://github.com/bazelbuild/remote-apis/blob/main/build/bazel/remote/asset/v1/remote_asset.proto
