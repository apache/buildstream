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

   # Optionally specify a relative staging destination file name
   # destination: filename

   # Specify the url. Using an alias defined in your project
   # configuration is encouraged. 'bst track' will update the
   # sha256sum in 'ref' to the downloaded file's sha256sum.
   url: upstream:foo

   # Specify the ref. It's a sha256sum of the file you download.
   ref: 6c9f6f68a131ec6381da82f2bff978083ed7f4f7991d931bfa767b7965ebc94b

"""
import os
from buildstream import utils
from ._downloadablefilesource import DownloadableFileSource


class RemoteSource(DownloadableFileSource):
    # pylint: disable=attribute-defined-outside-init

    def configure(self, node):
        super().configure(node)

        self.dest = self.node_get_member(node, str, "destination", os.path.basename(self.url))
        self.node_validate(node, DownloadableFileSource.COMMON_CONFIG_KEYS + ['destination'])

    def get_unique_key(self):
        return super().get_unique_key() + [self.dest]

    def stage(self, directory):
        # Same as in local plugin, don't use hardlinks to stage sources, they
        # are not write protected in the sandbox.
        with self.timed_activity("Staging remote file to {}".format(
                self.dest)):
            utils.safe_copy(self._get_mirror_file(), os.path.join(directory,
                                                                  self.dest))


def setup():
    return RemoteSource
