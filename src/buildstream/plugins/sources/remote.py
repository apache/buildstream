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

   # Optionally specify a relative staging filename.
   # If not specified, the basename of the url will be used.
   # filename: customfilename

   # Optionally specify whether the downloaded file should be
   # marked executable.
   # executable: true

   # Specify the url. Using an alias defined in your project
   # configuration is encouraged. 'bst source track' will update the
   # sha256sum in 'ref' to the downloaded file's sha256sum.
   url: upstream:foo

   # Specify the ref. It's a sha256sum of the file you download.
   ref: 6c9f6f68a131ec6381da82f2bff978083ed7f4f7991d931bfa767b7965ebc94b

See :ref:`built-in functionality doumentation <core_source_builtins>` for
details on common configuration options for sources.
"""
import os
from buildstream import DownloadableFileSource, SourceError, utils


class RemoteSource(DownloadableFileSource):
    # pylint: disable=attribute-defined-outside-init

    BST_MIN_VERSION = "2.0"

    def configure(self, node):
        super().configure(node)

        self.filename = node.get_str("filename", os.path.basename(self.url))
        self.executable = node.get_bool("executable", default=False)

        if os.sep in self.filename:
            raise SourceError(
                "{}: filename parameter cannot contain directories".format(self), reason="filename-contains-directory"
            )
        node.validate_keys(DownloadableFileSource.COMMON_CONFIG_KEYS + ["filename", "executable"])

    def get_unique_key(self):
        return super().get_unique_key() + [self.filename, self.executable]

    def stage(self, directory):
        # Same as in local plugin, don't use hardlinks to stage sources, they
        # are not write protected in the sandbox.
        dest = os.path.join(directory, self.filename)
        with self.timed_activity("Staging remote file to {}".format(dest)):

            utils.safe_copy(self._get_mirror_file(), dest)

            # To prevent user's umask introducing variability here, explicitly set
            # file modes.
            if self.executable:
                os.chmod(dest, 0o755)
            else:
                os.chmod(dest, 0o644)


def setup():
    return RemoteSource
