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
from buildstream.storage._casbaseddirectory import CasBasedDirectory
from buildstream import Source, SourceError, Consistency
from buildstream import utils
from buildstream.types import SourceRef
from buildstream.node import MappingNode


class WorkspaceSource(Source):
    # pylint: disable=attribute-defined-outside-init

    BST_STAGE_VIRTUAL_DIRECTORY = True

    def __init__(self, context, project, meta) -> None:
        super().__init__(context, project, meta)

        # Cached unique key
        self.__unique_key = None
        # the element source objects from the specified metasources
        self.__element_sources = []
        # the digest of the Directory following the import of the workspace
        self.__digest = None
        # the CasBasedDirectory which the path is imported into
        self.__cas_dir = None

    def set_element_sources(self, _element_sources: [Source]) -> None:
        self.__element_sources = _element_sources

    def get_element_sources(self) -> [Source]:
        return self.__element_sources

    def track(self) -> SourceRef:
        return None

    def configure(self, node: MappingNode) -> None:
        node.validate_keys(['path', 'ref', 'kind'])
        self.path = node.get_str('path')
        self.__digest = node.get_str('ref')

    def preflight(self) -> None:
        for source in self.get_element_sources():
            source.preflight()

    def get_ref(self) -> None:
        return None

    def load_ref(self, node: MappingNode) -> None:
        pass  # pragma: nocover

    def set_ref(self, ref: SourceRef, node: MappingNode) -> None:
        pass  # pragma: nocover

    def get_unique_key(self) -> (str, SourceRef):
        sourcecache = self._get_context().sourcecache

        if self.__cas_dir is None:
            self.__cas_dir = CasBasedDirectory(sourcecache.cas)

        if self.__digest is None:

            with self.timed_activity("Staging local files into CAS"):
                result = self.__cas_dir.import_files(self.path)
                if result.overwritten or result.ignored:
                    raise SourceError(
                        "Failed to stage source: files clash with existing directory",
                        reason='ensure-stage-dir-fail')
                self.__digest = self.__cas_dir._get_digest().hash

        # commit to cache if not cached
        if not sourcecache.contains(self):
            sourcecache.commit(self, [])

        #  now close down grpc channels
        sourcecache.cas.close_channel()
        assert not sourcecache.cas.has_open_grpc_channels()
        return (self.path, self.__digest)

    def init_workspace(self, directory: Directory) -> None:
        # for each source held by the workspace we must call init_workspace
        # those sources may override `init_workspace` expecting str or Directory
        # and this will need to be extracted from the directory passed to this method
        assert isinstance(directory, Directory)
        directory = directory.external_directory
        for source in self.get_element_sources():
            source._init_workspace(directory)

    def get_consistency(self):
        # always return cached state
        return Consistency.CACHED

    def fetch(self) -> None:
        pass  # pragma: nocover

    def stage(self, directory: Directory) -> None:
        # directory should always be a Directory object
        assert isinstance(directory, Directory)
        assert isinstance(self.__cas_dir, CasBasedDirectory)
        with self.timed_activity("Staging Workspace files"):
            result = directory.import_files(self.__cas_dir)

            if result.overwritten or result.ignored:
                raise SourceError(
                    "Failed to stage source: files clash with existing directory",
                    reason='ensure-stage-dir-fail')

    def _get_local_path(self) -> str:
        return self.path


# Plugin entry point
def setup() -> WorkspaceSource:
    return WorkspaceSource
