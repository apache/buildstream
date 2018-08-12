#
#  Copyright (C) 2017 Mathieu Bridon
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
#        Mathieu Bridon <bochecha@daitauha.fr>

"""
zip - stage files from zip archives
===================================

**Usage:**

.. code:: yaml

   # Specify the zip source kind
   kind: zip

   # Optionally specify a relative staging directory
   # directory: path/to/stage

   # Specify the zip url. Using an alias defined in your project
   # configuration is encouraged. 'bst track' will update the
   # sha256sum in 'ref' to the downloaded file's sha256sum.
   url: upstream:foo.zip

   # Specify the ref. It's a sha256sum of the file you download.
   ref: 6c9f6f68a131ec6381da82f2bff978083ed7f4f7991d931bfa767b7965ebc94b

   # Specify a glob pattern to indicate the base directory to extract
   # from the archive. The first matching directory will be used.
   #
   # Note that this is '*' by default since most standard release
   # archives contain a self named subdirectory at the root which
   # contains the files one normally wants to extract to build.
   #
   # To extract the root of the archive directly, this can be set
   # to an empty string.
   base-dir: '*'

.. attention::

   File permissions are not preserved. All extracted directories have
   permissions 0755 and all extracted files have permissions 0644.

"""

import os
import zipfile
import stat

from buildstream import SourceError
from buildstream import utils

from ._downloadablefilesource import DownloadableFileSource


class ZipSource(DownloadableFileSource):
    # pylint: disable=attribute-defined-outside-init

    def configure(self, node):
        super().configure(node)

        self.base_dir = self.node_get_member(node, str, 'base-dir', '*') or None

        self.node_validate(node, DownloadableFileSource.COMMON_CONFIG_KEYS + ['base-dir'])

    def get_unique_key(self):
        return super().get_unique_key() + [self.base_dir]

    def stage(self, directory):
        exec_rights = (stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO) & ~(stat.S_IWGRP | stat.S_IWOTH)
        noexec_rights = exec_rights & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        try:
            with zipfile.ZipFile(self._get_mirror_file()) as archive:
                base_dir = None
                if self.base_dir:
                    base_dir = self._find_base_dir(archive, self.base_dir)

                if base_dir:
                    members = self._extract_members(archive, base_dir)
                else:
                    members = archive.namelist()

                for member in members:
                    written = archive.extract(member, path=directory)

                    # zipfile.extract might create missing directories
                    rel = os.path.relpath(written, start=directory)
                    assert not os.path.isabs(rel)
                    rel = os.path.dirname(rel)
                    while rel:
                        os.chmod(os.path.join(directory, rel), exec_rights)
                        rel = os.path.dirname(rel)

                    if os.path.islink(written):
                        pass
                    elif os.path.isdir(written):
                        os.chmod(written, exec_rights)
                    else:
                        os.chmod(written, noexec_rights)

        except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError) as e:
            raise SourceError("{}: Error staging source: {}".format(self, e)) from e

    # Override and translate which filenames to extract
    def _extract_members(self, archive, base_dir):
        if not base_dir.endswith(os.sep):
            base_dir = base_dir + os.sep

        l = len(base_dir)
        for member in archive.infolist():
            if member.filename == base_dir:
                continue

            if member.filename.startswith(base_dir):
                member.filename = member.filename[l:]
                yield member

    # We want to iterate over all paths of an archive, but namelist()
    # is not enough because some archives simply do not contain the leading
    # directory paths for the archived files.
    def _list_archive_paths(self, archive):

        visited = {}
        for member in archive.infolist():

            # ZipInfo.is_dir() is only available in python >= 3.6, but all
            # it does is check for a trailing '/' in the name
            #
            if not member.filename.endswith('/'):

                # Loop over the components of a path, for a path of a/b/c/d
                # we will first visit 'a', then 'a/b' and then 'a/b/c', excluding
                # the final component
                components = member.filename.split('/')
                for i in range(len(components) - 1):
                    dir_component = '/'.join([components[j] for j in range(i + 1)])
                    if dir_component not in visited:
                        visited[dir_component] = True
                        try:
                            # Dont yield directory members which actually do
                            # exist in the archive
                            _ = archive.getinfo(dir_component)
                        except KeyError:
                            if dir_component != '.':
                                yield dir_component

                continue

            # Avoid considering the '.' directory, if any is included in the archive
            # this is to avoid the default 'base-dir: *' value behaving differently
            # depending on whether the archive was encoded with a leading '.' or not
            elif member.filename == '.' or member.filename == './':
                continue

            yield member.filename

    def _find_base_dir(self, archive, pattern):
        paths = self._list_archive_paths(archive)
        matches = sorted(list(utils.glob(paths, pattern)))
        if not matches:
            raise SourceError("{}: Could not find base directory matching pattern: {}".format(self, pattern))

        return matches[0]


def setup():
    return ZipSource
