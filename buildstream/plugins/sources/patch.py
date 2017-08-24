#!/usr/bin/env python3
#
#  Copyright Bloomberg Finance LP
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

"""A Source implementation for applying local patches

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
import hashlib
from buildstream import Source, SourceError, Consistency
from buildstream import utils


class PatchSource(Source):

    def configure(self, node):
        project = self.get_project()

        self.path = self.node_get_member(node, str, "path")
        self.strip_level = self.node_get_member(node, int, "strip-level", 1)
        self.fullpath = os.path.join(project.directory, self.path)

    def preflight(self):
        # Check if the configured file really exists
        if not os.path.exists(self.fullpath):
            raise SourceError("Specified path '%s' does not exist" % self.path)
        elif not os.path.isfile(self.fullpath):
            raise SourceError("Specified path '%s' must be a file" % self.path)

        # Check if patch is installed, get the binary at the same time
        self.host_patch = utils.get_host_tool("patch")

    def get_unique_key(self):
        return [self.path, _sha256sum(self.fullpath), self.strip_level]

    def get_consistency(self):
        return Consistency.CACHED

    def get_ref(self):
        # We dont have a ref, we"re a local file...
        return None

    def set_ref(self, ref, node):
        pass

    def fetch(self):
        # Nothing to do here for a local source
        pass

    def stage(self, directory):
        with self.timed_activity("Applying local patch: {}".format(self.path)):
            if not os.path.isdir(directory):
                raise SourceError(
                    "Patch directory '{}' does not exist".format(directory))
            elif not os.listdir(directory):
                raise SourceError("Empty patch directory '{}'".format(directory))
            strip_level_option = "-p{}".format(self.strip_level)
            self.call([self.host_patch, strip_level_option, "-i", self.fullpath, "-d", directory],
                      fail="Failed to apply patch {}".format(self.path))


# Get the sha256 sum for the content of a file
def _sha256sum(filename):
    h = hashlib.sha256()
    with open(filename, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()


# Plugin entry point
def setup():
    return PatchSource
