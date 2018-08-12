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
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#        Ed Baunton <ebaunton1@bloomberg.net>

"""
remote - stage files from remote urls
=====================================

**Usage:**

.. code:: yaml

   # Specify the remote source kind
   kind: remote

   # Optionally specify a relative staging directory
   # directory: path/to/stage

   # Optionally specify a relative staging filename.
   # If not specified, the basename of the url will be used.
   # filename: customfilename

   # Specify the url. Using an alias defined in your project
   # configuration is encouraged. 'bst track' will update the
   # sha256sum in 'ref' to the downloaded file's sha256sum.
   url: upstream:foo

   # Specify the ref. It's a sha256sum of the file you download.
   ref: 6c9f6f68a131ec6381da82f2bff978083ed7f4f7991d931bfa767b7965ebc94b

.. note::

   The ``remote`` plugin is available since :ref:`format version 10 <project_format_version>`

"""
import os
import stat
from buildstream import SourceError, utils
from ._downloadablefilesource import DownloadableFileSource


class RemoteSource(DownloadableFileSource):
    # pylint: disable=attribute-defined-outside-init

    def configure(self, node):
        super().configure(node)

        self.filename = self.node_get_member(node, str, 'filename', os.path.basename(self.url))

        if os.sep in self.filename:
            raise SourceError('{}: filename parameter cannot contain directories'.format(self),
                              reason="filename-contains-directory")
        self.node_validate(node, DownloadableFileSource.COMMON_CONFIG_KEYS + ['filename'])

    def get_unique_key(self):
        return super().get_unique_key() + [self.filename]

    def stage(self, directory):
        # Same as in local plugin, don't use hardlinks to stage sources, they
        # are not write protected in the sandbox.
        dest = os.path.join(directory, self.filename)
        with self.timed_activity("Staging remote file to {}".format(dest)):
            utils.safe_copy(self._get_mirror_file(), dest)
            os.chmod(dest, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)


def setup():
    return RemoteSource
