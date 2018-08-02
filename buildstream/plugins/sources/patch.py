#
#  Copyright Bloomberg Finance LP
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
#        Chandan Singh <csingh43@bloomberg.net>
#        Tiago Gomes <tiago.gomes@codethink.co.uk>

"""
patch - apply locally stored patches
====================================

**Host dependencies:**

  * patch

**Usage:**

.. code:: yaml

   # Specify the local source kind
   kind: patch

   # Specify the project relative path to a patch file
   path: files/somefile.diff

   # Optionally specify the root directory for the patch
   # directory: path/to/stage

   # Optionally specify the strip level, defaults to 1
   strip-level: 1

"""

import os
from buildstream import Source, SourceError, Consistency
from buildstream import utils


class PatchSource(Source):
    # pylint: disable=attribute-defined-outside-init

    def configure(self, node):
        self.path = self.node_get_project_path(node, 'path',
                                               check_is_file=True)
        self.strip_level = self.node_get_member(node, int, "strip-level", 1)
        self.fullpath = os.path.join(self.get_project_directory(), self.path)

    def preflight(self):
        # Check if patch is installed, get the binary at the same time
        self.host_patch = utils.get_host_tool("patch")

    def get_unique_key(self):
        return [self.path, utils.sha256sum(self.fullpath), self.strip_level]

    def get_consistency(self):
        return Consistency.CACHED

    def load_ref(self, node):
        pass

    def get_ref(self):
        return None  # pragma: nocover

    def set_ref(self, ref, node):
        pass  # pragma: nocover

    def fetch(self):
        # Nothing to do here for a local source
        pass  # pragma: nocover

    def stage(self, directory):
        with self.timed_activity("Applying local patch: {}".format(self.path)):

            # Bail out with a comprehensive message if the target directory is empty
            if not os.listdir(directory):
                raise SourceError("Nothing to patch in directory '{}'".format(directory),
                                  reason="patch-no-files")

            strip_level_option = "-p{}".format(self.strip_level)
            self.call([self.host_patch, strip_level_option, "-i", self.fullpath, "-d", directory],
                      fail="Failed to apply patch {}".format(self.path))


# Plugin entry point
def setup():
    return PatchSource
