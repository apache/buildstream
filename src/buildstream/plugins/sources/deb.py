#  Copyright (C) 2017 Codethink Limited
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
#        Phillip Smyth <phillip.smyth@codethink.co.uk>
#        Jonathan Maw <jonathan.maw@codethink.co.uk>
#        Richard Maw <richard.maw@codethink.co.uk>

"""
deb - stage files from .deb packages
====================================

**Host dependencies:**

  * arpy (python package)

**Usage:**

.. code:: yaml

   # Specify the deb source kind
   kind: deb

   # Specify the deb url. Using an alias defined in your project
   # configuration is encouraged. 'bst source track' will update the
   # sha256sum in 'ref' to the downloaded file's sha256sum.
   url: upstream:foo.deb

   # Specify the ref. It's a sha256sum of the file you download.
   ref: 6c9f6f68a131ec6381da82f2bff978083ed7f4f7991d931bfa767b7965ebc94b

   # Specify the basedir to return only the specified dir and its children
   base-dir: ''

See :ref:`built-in functionality doumentation <core_source_builtins>` for
details on common configuration options for sources.
"""

import tarfile
from contextlib import contextmanager
import arpy

from .tar import TarSource


class DebSource(TarSource):
    # pylint: disable=attribute-defined-outside-init

    def configure(self, node):
        super().configure(node)

        self.base_dir = node.get_str("base-dir", None)

    def preflight(self):
        return

    @contextmanager
    def _get_tar(self):
        with open(self._get_mirror_file(), "rb") as deb_file:
            arpy_archive = arpy.Archive(fileobj=deb_file)
            arpy_archive.read_all_headers()
            data_tar_arpy = [v for k, v in arpy_archive.archived_files.items() if b"data.tar" in k][0]
            # ArchiveFileData is not enough like a file object for tarfile to use.
            # Monkey-patching a seekable method makes it close enough for TarFile to open.
            data_tar_arpy.seekable = lambda *args: True
            tar = tarfile.open(fileobj=data_tar_arpy, mode="r:*")
            yield tar


def setup():
    return DebSource
