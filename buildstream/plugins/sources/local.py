#!/usr/bin/env python3
#
#  Copyright (C) 2016 Codethink Limited
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

"""A Source implementation for staging local project files

**Usage:**

.. code:: yaml

   # Specify the local source kind
   kind: local

   # Optionally specify a relative staging directory
   # directory: path/to/stage

   # Specify the project relative path to a file or directory
   path: files/somefile.txt
"""

import os
import hashlib
from buildstream import Source, SourceError
from buildstream import utils


class LocalSource(Source):

    def configure(self, node):
        project = self.get_project()

        self.path = self.node_get_member(node, str, 'path')
        self.fullpath = os.path.join(project.directory, self.path)

    def preflight(self):
        # Check if the configured file or directory really exists
        if not os.path.exists(self.fullpath):
            raise SourceError("Specified path '%s' does not exist" % self.path)

    def get_unique_key(self):
        # Get a list of tuples of the the project relative paths and fullpaths
        if os.path.isdir(self.fullpath):
            filelist = utils.list_relative_paths(self.fullpath)
            filelist = [(relpath, os.path.join(self.fullpath, relpath)) for relpath in filelist]
        else:
            filelist = [(self.path, self.fullpath)]

        # Return a list of (relative filename, sha256 digest) tuples, a sorted list
        # has already been returned by list_relative_paths()
        return [(relpath, sha256sum(fullpath)) for relpath, fullpath in filelist]

    def consistent(self):
        return True

    # We dont have a ref, we're a local file...
    def get_ref(self):
        return None

    def set_ref(self, ref, node):
        pass

    def fetch(self):
        # Nothing to do here for a local source
        pass

    def stage(self, directory):

        # Dont use hardlinks to stage sources, they are not write protected
        # in the sandbox.
        with self.timed_activity("Staging local files at {}".format(self.path)):
            if os.path.isdir(self.fullpath):
                utils.copy_files(self.fullpath, directory)
            else:
                destfile = os.path.join(directory, os.path.basename(self.path))
                utils.safe_copy(self.fullpath, destfile)


# Get the sha256 sum for the content of a file
def sha256sum(filename):
    h = hashlib.sha256()
    with open(filename, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()


# Plugin entry point
def setup():
    return LocalSource
