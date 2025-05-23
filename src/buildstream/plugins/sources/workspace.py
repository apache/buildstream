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
:orphan:

workspace - stage an opened workspace directory
===============================================

**Usage:**

The workspace plugin must not be directly used. This plugin is used as the
kind for a synthetic node representing the sources of an element with an open
workspace.


Reporting :class:`.SourceInfo`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The workspace source reports the project relative or absolute path to the open
workspace as the *url*.

Further, the workspace source reports the
:attr:`SourceInfoMedium.WORKSPACE <buildstream.source.SourceInfoMedium.WORKSPACE>` *medium* and the
:attr:`SourceVersionType.CAS_DIGEST <buildstream.source.SourceVersionType.CAS_DIGEST>` *version_type*,
for which it reports the CAS digest of the workspace source as the *version*.

The *guess_version* of a workspace source is meaningless and omitted.

.. attention::

   Observing a SourceInfo with the ``SourceInfoMedium.WORKSPACE`` in the output of
   :ref:`bst show --format %{source-info} <invoking_show>` is most likely undesirable, given
   that you are likely interested in observing the source provenance information of the
   project in a clean state rather than in a state with open workspaces.
"""

import os

from buildstream import Source, SourceError, SourceInfoMedium, SourceVersionType, Directory, MappingNode
from buildstream.types import SourceRef


class WorkspaceSource(Source):
    # pylint: disable=attribute-defined-outside-init

    BST_MIN_VERSION = "2.0"
    BST_STAGE_VIRTUAL_DIRECTORY = True

    # the digest of the Directory following the import of the workspace
    __digest = None
    # the cache key of the last workspace build
    __last_build = None

    def configure(self, node: MappingNode) -> None:
        node.validate_keys(["path", "last_build", "kind"])
        self.path = node.get_str("path")
        self.__last_build = node.get_str("last_build")

    def preflight(self) -> None:
        pass  # pragma: nocover

    def is_cached(self):
        return True

    def is_resolved(self):
        return os.path.exists(self._get_local_path())

    def get_unique_key(self):
        #
        # As a core plugin, we use some private API to optimize file hashing.
        #
        # * Use Source._cache_directory() to prepare a Directory
        # * Do the regular staging activity into the Directory
        # * Use the hash of the cached digest as the unique key
        #
        self.__ensure_digest()
        return self.__digest.hash

    def get_ref(self) -> None:
        return None

    def load_ref(self, node: MappingNode) -> None:
        pass  # pragma: nocover

    def set_ref(self, ref: SourceRef, node: MappingNode) -> None:
        pass  # pragma: nocover

    # init_workspace()
    #
    # Raises AssertionError: existing workspaces should not be reinitialized
    def init_workspace_directory(self, directory: Directory) -> None:
        raise AssertionError("Attempting to re-open an existing workspace")

    def fetch(self, *, previous_sources_dir=None) -> None:  # pylint: disable=arguments-differ
        pass  # pragma: nocover

    def stage_directory(self, directory):
        #
        # We've already prepared the CAS while resolving the cache key which
        # will happen before staging.
        #
        # Now just retrieve the previously cached content to stage.
        #
        assert isinstance(directory, Directory)
        assert self.__digest is not None
        with self._cache_directory(digest=self.__digest) as cached_directory:
            directory._import_files_internal(cached_directory, collect_result=False)

    def collect_source_info(self):
        self.__ensure_digest()
        version = "{}/{}".format(self.__digest.hash, self.__digest.size_bytes)
        return [self.create_source_info(self.path, SourceInfoMedium.WORKSPACE, SourceVersionType.CAS_DIGEST, version)]

    # As a core element, we speed up some scenarios when this is used for
    # a junction, by providing the local path to this content directly.
    #
    def _get_local_path(self) -> str:
        return self.path

    # Ensure that the digest is resolved
    #
    def __ensure_digest(self):
        if not self.__digest:
            with self._cache_directory() as directory:
                self.__do_stage(directory)
                self.__digest = directory._get_digest()

    # Staging is implemented internally, we preemptively put it in the CAS
    # as a side effect of resolving the cache key, at stage time we just
    # do an internal CAS stage.
    #
    def __do_stage(self, directory: Directory) -> None:
        assert isinstance(directory, Directory)
        with self.timed_activity("Staging local files"):
            result = directory._import_files_internal(self.path, properties=["mtime"])
            assert result is not None

            if result.overwritten or result.ignored:
                raise SourceError(
                    "Failed to stage source: files clash with existing directory", reason="ensure-stage-dir-fail"
                )


# Plugin entry point
def setup():
    return WorkspaceSource
