#
#  Copyright (C) 2019 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.

"""
:orphan:

workspace - stage an opened workspace directory
===============================================

**Usage:**

The workspace plugin must not be directly used. This plugin is used as the
kind for a synthetic node representing the sources of an element with an open
workspace. The node constructed would be specified as follows:

.. code:: yaml

   # Specify the workspace source kind
   kind: workspace

   # Specify the absolute path to the directory
   path: /path/to/workspace
"""

import os

from buildstream import Source, SourceError, Directory, MappingNode
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
        if not self.__digest:
            with self._cache_directory() as directory:
                self.__do_stage(directory)
                self.__digest = directory._get_digest()

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
    def init_workspace(self, directory: Directory) -> None:
        raise AssertionError("Attempting to re-open an existing workspace")

    def fetch(self) -> None:  # pylint: disable=arguments-differ
        pass  # pragma: nocover

    def stage(self, directory):
        #
        # We've already prepared the CAS while resolving the cache key which
        # will happen before staging.
        #
        # Now just retrieve the previously cached content to stage.
        #
        assert isinstance(directory, Directory)
        assert self.__digest is not None
        with self._cache_directory(digest=self.__digest) as cached_directory:
            directory.import_files(cached_directory)

    # As a core element, we speed up some scenarios when this is used for
    # a junction, by providing the local path to this content directly.
    #
    def _get_local_path(self) -> str:
        return self.path

    # Staging is implemented internally, we preemptively put it in the CAS
    # as a side effect of resolving the cache key, at stage time we just
    # do an internal CAS stage.
    #
    def __do_stage(self, directory: Directory) -> None:
        assert isinstance(directory, Directory)
        with self.timed_activity("Staging local files"):
            result = directory.import_files(self.path, properties=["mtime"])

            if result.overwritten or result.ignored:
                raise SourceError(
                    "Failed to stage source: files clash with existing directory", reason="ensure-stage-dir-fail"
                )


# Plugin entry point
def setup() -> WorkspaceSource:
    return WorkspaceSource
