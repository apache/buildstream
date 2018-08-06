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

   # Optionally specify a relative staging directory
   # directory: path/to/stage

   # Specify the project relative path to a file or directory
   path: files/somefile.txt
"""

import os
import stat
from buildstream import Source, Consistency
from buildstream import utils


class LocalSource(Source):
    # pylint: disable=attribute-defined-outside-init

    def __init__(self, context, project, meta):
        super().__init__(context, project, meta)

        # Cached unique key to avoid multiple file system traversal if the unique key is requested multiple times.
        self.__unique_key = None

    def configure(self, node):
        self.node_validate(node, ['path'] + Source.COMMON_CONFIG_KEYS)
        self.path = self.node_get_project_path(node, 'path')
        self.fullpath = os.path.join(self.get_project_directory(), self.path)

    def preflight(self):
        pass

    def get_unique_key(self):
        if self.__unique_key is None:
            # Get a list of tuples of the the project relative paths and fullpaths
            if os.path.isdir(self.fullpath):
                filelist = utils.list_relative_paths(self.fullpath)
                filelist = [(relpath, os.path.join(self.fullpath, relpath)) for relpath in filelist]
            else:
                filelist = [(self.path, self.fullpath)]

            # Return a list of (relative filename, sha256 digest) tuples, a sorted list
            # has already been returned by list_relative_paths()
            self.__unique_key = [(relpath, unique_key(fullpath)) for relpath, fullpath in filelist]
        return self.__unique_key

    def get_consistency(self):
        return Consistency.CACHED

    # We dont have a ref, we're a local file...
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

        # Dont use hardlinks to stage sources, they are not write protected
        # in the sandbox.
        with self.timed_activity("Staging local files at {}".format(self.path)):

            if os.path.isdir(self.fullpath):
                files = list(utils.list_relative_paths(self.fullpath, list_dirs=True))
                utils.copy_files(self.fullpath, directory, files=files)
            else:
                destfile = os.path.join(directory, os.path.basename(self.path))
                files = [os.path.basename(self.path)]
                utils.safe_copy(self.fullpath, destfile)

            for f in files:
                # Non empty directories are not listed by list_relative_paths
                dirs = f.split(os.sep)
                for i in range(1, len(dirs)):
                    d = os.path.join(directory, *(dirs[:i]))
                    assert os.path.isdir(d) and not os.path.islink(d)
                    os.chmod(d, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

                path = os.path.join(directory, f)
                if os.path.islink(path):
                    pass
                elif os.path.isdir(path):
                    os.chmod(path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
                else:
                    st = os.stat(path)
                    if st.st_mode & stat.S_IXUSR:
                        os.chmod(path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
                    else:
                        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)


# Create a unique key for a file
def unique_key(filename):

    # Return some hard coded things for files which
    # have no content to calculate a key for
    if os.path.isdir(filename):
        return "0"
    elif os.path.islink(filename):
        # For a symbolic link, use the link target as it's unique identifier
        return os.readlink(filename)

    return utils.sha256sum(filename)


# Plugin entry point
def setup():
    return LocalSource
