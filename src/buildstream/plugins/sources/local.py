#
#  Copyright (C) 2018 Codethink Limited
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
#
#  Authors:
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
#        Tiago Gomes <tiago.gomes@codethink.co.uk>

"""
local - stage local files and directories
=========================================

**Usage:**

.. code:: yaml

   # Specify the local source kind
   kind: local

   # Specify the project relative path to a file or directory
   path: files/somefile.txt

See :ref:`built-in functionality doumentation <core_source_builtins>` for
details on common configuration options for sources.
"""

import os
from buildstream.storage.directory import Directory
from buildstream import Source, SourceError


class LocalSource(Source):
    # pylint: disable=attribute-defined-outside-init

    BST_MIN_VERSION = "2.0"

    BST_STAGE_VIRTUAL_DIRECTORY = True
    BST_KEY_REQUIRES_STAGE = True

    __unique_key = None

    def configure(self, node):
        node.validate_keys(["path", *Source.COMMON_CONFIG_KEYS])
        self.path = self.node_get_project_path(node.get_scalar("path"))
        self.fullpath = os.path.join(self.get_project_directory(), self.path)

    def preflight(self):
        pass

    def is_resolved(self):
        return True

    def is_cached(self):
        return True

    # We dont have a ref, we're a local file...
    def load_ref(self, node):
        pass

    def get_ref(self):
        return None  # pragma: nocover

    def set_ref(self, ref, node):
        pass  # pragma: nocover

    def fetch(self):  # pylint: disable=arguments-differ
        # Nothing to do here for a local source
        pass  # pragma: nocover

    def stage(self, directory):
        # directory should always be a Directory object
        assert isinstance(directory, Directory)
        with self.timed_activity("Staging local files into CAS"):
            if os.path.isdir(self.fullpath) and not os.path.islink(self.fullpath):
                result = directory.import_files(self.fullpath)
            else:
                result = directory.import_single_file(self.fullpath)

            if result.overwritten or result.ignored:
                raise SourceError(
                    "Failed to stage source: files clash with existing directory", reason="ensure-stage-dir-fail"
                )

    def _get_local_path(self):
        return self.fullpath


# Plugin entry point
def setup():
    return LocalSource
