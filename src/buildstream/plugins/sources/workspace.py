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

from buildstream.storage.directory import Directory
from buildstream import Source, SourceError
from buildstream.types import SourceRef
from buildstream.node import MappingNode


class WorkspaceSource(Source):
    # pylint: disable=attribute-defined-outside-init

    BST_MIN_VERSION = "2.0"

    BST_STAGE_VIRTUAL_DIRECTORY = True
    BST_KEY_REQUIRES_STAGE = True

    # Cached unique key
    __unique_key = None
    # the digest of the Directory following the import of the workspace
    __digest = None
    # the cache key of the last workspace build
    __last_build = None

    def track(self) -> SourceRef:  # pylint: disable=arguments-differ
        return None

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

    def stage(self, directory: Directory) -> None:
        assert isinstance(directory, Directory)
        with self.timed_activity("Staging local files"):
            result = directory.import_files(self.path, properties=["mtime"])

            if result.overwritten or result.ignored:
                raise SourceError(
                    "Failed to stage source: files clash with existing directory", reason="ensure-stage-dir-fail"
                )

    def _get_local_path(self) -> str:
        return self.path


# Plugin entry point
def setup() -> WorkspaceSource:
    return WorkspaceSource
