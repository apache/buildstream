#
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
#        Jonathan Maw <jonathan.maw@codethink.co.uk>

"""
tar - stage files from tar archives
===================================

**Host dependencies:**

  * lzip (for .tar.lz files)

**Usage:**

.. code:: yaml

   # Specify the tar source kind
   kind: tar

   # Specify the tar url. Using an alias defined in your project
   # configuration is encouraged. 'bst source track' will update the
   # sha256sum in 'ref' to the downloaded file's sha256sum.
   url: upstream:foo.tar

   # Specify the ref. It's a sha256sum of the file you download.
   ref: 6c9f6f68a131ec6381da82f2bff978083ed7f4f7991d931bfa767b7965ebc94b

   # Specify a glob pattern to indicate the base directory to extract
   # from the tarball. The first matching directory will be used.
   #
   # Note that this is '*' by default since most standard release
   # tarballs contain a self named subdirectory at the root which
   # contains the files one normally wants to extract to build.
   #
   # To extract the root of the tarball directly, this can be set
   # to an empty string.
   base-dir: '*'

See :ref:`built-in functionality doumentation <core_source_builtins>` for
details on common configuration options for sources.
"""

import os
import tarfile
from contextlib import contextmanager
from tempfile import TemporaryFile

from buildstream import DownloadableFileSource, SourceError
from buildstream import utils


class ReadableTarInfo(tarfile.TarInfo):
    """
           The goal is to override `TarFile`'s `extractall` semantics by ensuring that on extraction, the
           files are readable by the owner of the file. This is done by overriding the accessor for the
           `mode` attribute in `TarInfo`, the class that encapsulates the internal meta-data of the tarball,
           so that the owner-read bit is always set.
    """

    @property
    def mode(self):
        # Respect umask instead of the file mode stored in the archive.
        # The only bit used from the embedded mode is the executable bit for files.
        umask = utils.get_umask()
        if self.isdir() or bool(self.__permission | 0o100):
            return 0o777 & ~umask
        else:
            return 0o666 & ~umask

    @mode.setter
    def mode(self, permission):
        self.__permission = permission  # pylint: disable=attribute-defined-outside-init


class TarSource(DownloadableFileSource):
    # pylint: disable=attribute-defined-outside-init

    BST_MIN_VERSION = "2.0"

    def configure(self, node):
        super().configure(node)

        self.base_dir = node.get_str("base-dir", "*")
        node.validate_keys(DownloadableFileSource.COMMON_CONFIG_KEYS + ["base-dir"])

    def preflight(self):
        self.host_lzip = None
        if self.url.endswith(".lz"):
            self.host_lzip = utils.get_host_tool("lzip")

    def get_unique_key(self):
        return super().get_unique_key() + [self.base_dir]

    @contextmanager
    def _run_lzip(self):
        assert self.host_lzip
        with TemporaryFile() as lzip_stdout:
            with open(self._get_mirror_file(), "r") as lzip_file:
                self.call([self.host_lzip, "-d"], stdin=lzip_file, stdout=lzip_stdout)

            lzip_stdout.seek(0, 0)
            yield lzip_stdout

    @contextmanager
    def _get_tar(self):
        if self.url.endswith(".lz"):
            with self._run_lzip() as lzip_dec:
                with tarfile.open(fileobj=lzip_dec, mode="r:", tarinfo=ReadableTarInfo) as tar:
                    yield tar
        else:
            with tarfile.open(self._get_mirror_file(), tarinfo=ReadableTarInfo) as tar:
                yield tar

    def stage(self, directory):
        try:
            with self._get_tar() as tar:
                base_dir = None
                if self.base_dir:
                    base_dir = self._find_base_dir(tar, self.base_dir)

                def filter_non_dev(tarfiles):
                    for file in tarfiles:
                        if not file.isdev():
                            yield file

                if base_dir:
                    tar.extractall(
                        path=directory, members=filter_non_dev(self._extract_members(tar, base_dir, directory))
                    )
                else:
                    tar.extractall(path=directory, members=filter_non_dev(tar.getmembers()))

        except (tarfile.TarError, OSError) as e:
            raise SourceError("{}: Error staging source: {}".format(self, e)) from e

    # Override and translate which filenames to extract
    def _extract_members(self, tar, base_dir, target_dir):

        # Assert that a tarfile is safe to extract; specifically, make
        # sure that we don't do anything outside of the target
        # directory (this is possible, if, say, someone engineered a
        # tarfile to contain paths that start with ..).
        def assert_safe(member):
            final_path = os.path.abspath(os.path.join(target_dir, member.path))
            if not final_path.startswith(target_dir):
                raise SourceError(
                    "{}: Tarfile attempts to extract outside the staging area: "
                    "{} -> {}".format(self, member.path, final_path)
                )

            if member.islnk():
                linked_path = os.path.abspath(os.path.join(target_dir, member.linkname))
                if not linked_path.startswith(target_dir):
                    raise SourceError(
                        "{}: Tarfile attempts to hardlink outside the staging area: "
                        "{} -> {}".format(self, member.path, final_path)
                    )

            # Don't need to worry about symlinks because they're just
            # files here and won't be able to do much harm once we are
            # in a sandbox.

        if not base_dir.endswith(os.sep):
            base_dir = base_dir + os.sep

        L = len(base_dir)
        for member in tar.getmembers():

            # First, ensure that a member never starts with `./`
            if member.path.startswith("./"):
                member.path = member.path[2:]
            if member.islnk() and member.linkname.startswith("./"):
                member.linkname = member.linkname[2:]

            # Now extract only the paths which match the normalized path
            if member.path.startswith(base_dir):
                # Hardlinks are smart and collapse into the "original"
                # when their counterpart doesn't exist. This means we
                # only need to modify links to files whose location we
                # change.
                #
                # Since we assert that we're not linking to anything
                # outside the target directory, this should only ever
                # be able to link to things inside the target
                # directory, so we should cover all bases doing this.
                #
                if member.islnk() and member.linkname.startswith(base_dir):
                    member.linkname = member.linkname[L:]

                member.path = member.path[L:]

                assert_safe(member)
                yield member

    # We want to iterate over all paths of a tarball, but getmembers()
    # is not enough because some tarballs simply do not contain the leading
    # directory paths for the archived files.
    def _list_tar_paths(self, tar):

        visited = set()
        for member in tar.getmembers():

            # Remove any possible leading './', offer more consistent behavior
            # across tarballs encoded with or without a leading '.'
            member_name = member.name.lstrip("./")

            if not member.isdir():

                # Loop over the components of a path, for a path of a/b/c/d
                # we will first visit 'a', then 'a/b' and then 'a/b/c', excluding
                # the final component
                components = member_name.split("/")
                for i in range(len(components) - 1):
                    dir_component = "/".join([components[j] for j in range(i + 1)])
                    if dir_component not in visited:
                        visited.add(dir_component)
                        try:
                            # Dont yield directory members which actually do
                            # exist in the archive
                            _ = tar.getmember(dir_component)
                        except KeyError:
                            if dir_component != ".":
                                yield dir_component

                continue

            # Avoid considering the '.' directory, if any is included in the archive
            # this is to avoid the default 'base-dir: *' value behaving differently
            # depending on whether the tarball was encoded with a leading '.' or not
            if member_name == ".":
                continue

            yield member_name

    def _find_base_dir(self, tar, pattern):
        paths = self._list_tar_paths(tar)
        matches = sorted(list(utils.glob(paths, pattern)))
        if not matches:
            raise SourceError("{}: Could not find base directory matching pattern: {}".format(self, pattern))

        return matches[0]


def setup():
    return TarSource
