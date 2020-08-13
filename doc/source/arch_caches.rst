
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
for storing directory and file information as defined in Googles `REAPI`_.

:ref:`bst-artifact-server <artifact_command_reference>` runs a `grpc`_ CAS
service (also defined in REAPI) that both artifact and source cache use,
allowing them to download and upload files to a remote service.

Artifact caches
---------------

Artifacts store build results of an element which is then referred to by its
cache key (described in :ref:`cachekeys`). The artifacts information is then
stored in a protocol buffer, defined in ``artifact.proto``, which includes
metadata such as the digest of the files root; strong and weak keys; and log
files digests. The digests point to locations in the CAS of relavant files and
directories, allowing BuildStream to query remote CAS servers for this
information.

:ref:`bst-artifact-server <artifact_command_reference>` uses grpc to implement
the Remote Asset API for an artifact service, that BuildStream then uses to
query, retrieve and update artifact references, before using this information to
download the files and other data from the remote CAS.

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

Similar to artifacts, :ref:`bst-artifact-server <artifact_command_reference>`
uses grpc to implement the Remote Asset API that allows BuildStream to query for
these source digests, which can then be used to retrieve sources from a CAS.

.. note::

   Not all plugins use the same result as the staged output for workspaces. As a
   result when initialising a workspace, BuildStream may require fetching the
   original source if it only has the source in the source cache.

.. _protocol buffers: https://developers.google.com/protocol-buffers/docs/overview
.. _grpc: https://grpc.io
.. _REAPI: https://github.com/bazelbuild/remote-apis
