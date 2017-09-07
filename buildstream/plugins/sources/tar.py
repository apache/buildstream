#!/usr/bin/env python3
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

"""A source implementation for staging tar files

**Usage:**

.. code:: yaml

   # Specify the tar source kind
   kind: tar

   # Specify the tar url. Using an alias defined in your project
   # configuration is encouraged. 'bst track' will update the
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
"""

import os
import urllib.request
import urllib.error
import tarfile
import tempfile

from buildstream import Source, SourceError, Consistency
from buildstream import utils


class TarSource(Source):

    def configure(self, node):
        project = self.get_project()

        self.node_validate(node, ['url', 'ref', 'base-dir'] + Source.COMMON_CONFIG_KEYS)

        self.original_url = self.node_get_member(node, str, 'url')
        self.ref = self.node_get_member(node, str, 'ref', '') or None
        self.base_dir = self.node_get_member(node, str, 'base-dir', '*') or None
        self.url = project.translate_url(self.original_url)

    def preflight(self):
        return

    def get_unique_key(self):
        return [self.original_url, self.ref, self.base_dir]

    def get_consistency(self):
        if self.ref is None:
            return Consistency.INCONSISTENT

        if os.path.isfile(self._get_mirror_file()):
            return Consistency.CACHED
        else:
            return Consistency.RESOLVED

    def get_ref(self):
        return self.ref

    def set_ref(self, ref, node):
        node['ref'] = self.ref = ref

    def track(self):
        # there is no 'track' field in the source to determine what/whether
        # or not to update refs, because tracking a ref is always a conscious
        # decision by the user.
        with self.timed_activity("Tracking {}".format(self.url),
                                 silent_nested=True):
            new_ref = self._ensure_mirror()
            if self.ref and self.ref != new_ref:
                detail = "When tracking, new ref differs from current ref:\n" \
                    + "  Tracked URL: {}\n".format(self.url) \
                    + "  Current ref: {}\n".format(self.ref) \
                    + "  New ref: {}\n".format(new_ref)
                self.warn("Potential man-in-the-middle attack!", detail=detail)
            return new_ref

    def fetch(self):
        if os.path.isfile(self._get_mirror_file()):
            return

        # Download the file, raise hell if the sha256sums don't match,
        # and mirror the file otherwise.
        with self.timed_activity("Fetching {}".format(self.url), silent_nested=True):
            sha256 = self._ensure_mirror()
            if sha256 != self.ref:
                raise SourceError("Tar downloaded from {} has sha256sum '{}', not '{}'!"
                                  .format(self.url, sha256, self.ref))

    def stage(self, directory):
        try:
            with tarfile.open(self._get_mirror_file()) as tar:
                base_dir = None
                if self.base_dir:
                    base_dir = self._find_base_dir(tar, self.base_dir)

                if base_dir:
                    tar.extractall(path=directory, members=self._extract_members(tar, base_dir))
                else:
                    tar.extractall(path=directory)

        except (tarfile.TarError, OSError) as e:
            raise SourceError("{}: Error staging source: {}".format(self, e)) from e

    def _ensure_mirror(self):
        # Downloads from the url and caches it according to its sha256sum.
        try:
            with self.tempdir() as td:
                # Using basename because there needs to be a filename, and 'foo'
                # would be too silly.
                temp_dest = os.path.join(td, os.path.basename(self.url))

                local_file, _ = urllib.request.urlretrieve(self.url, temp_dest)
                if local_file != temp_dest:
                    raise SourceError("Expected to download file to '{}', downloaded to '{}' instead!"
                                      .format(temp_dest, local_file))

                # Make sure url-specific mirror dir exists.
                if not os.path.isdir(self._get_mirror_dir()):
                    os.makedirs(self._get_mirror_dir())

                # Store by sha256sum
                sha256 = utils.sha256sum(local_file)
                # Even if the file already exists, move the new file over.
                # In case the old file was corrupted somehow.
                os.rename(local_file, self._get_mirror_file(sha256))

                return sha256
        except (urllib.error.URLError, urllib.error.ContentTooShortError, OSError) as e:
            raise SourceError("{}: Error mirroring {}: {}"
                              .format(self, self.url, e)) from e

    def _get_mirror_dir(self):
        return os.path.join(self.get_mirror_directory(),
                            utils.url_directory_name(self.original_url))

    def _get_mirror_file(self, sha=None):
        return os.path.join(self._get_mirror_dir(), sha or self.ref)

    # Override and translate which filenames to extract
    def _extract_members(self, tar, base_dir):
        if not base_dir.endswith(os.sep):
            base_dir = base_dir + os.sep

        l = len(base_dir)
        for member in tar.getmembers():
            if member.path.startswith(base_dir):
                member.path = member.path[l:]
                yield member

    # We want to iterate over all paths of a tarball, but getmembers()
    # is not enough because some tarballs simply do not contain the leading
    # directory paths for the archived files.
    def _list_tar_paths(self, tar, dirs_only=False):

        visited = {}
        for member in tar.getmembers():
            if not member.isdir():

                # Loop over the components of a path, for a path of a/b/c/d
                # we will first visit 'a', then 'a/b' and then 'a/b/c', excluding
                # the final component
                components = member.name.split('/')
                for i in range(len(components) - 1):
                    dir_component = '/'.join([components[j] for j in range(i + 1)])
                    if dir_component not in visited:
                        visited[dir_component] = True
                        try:
                            # Dont yield directory members which actually do
                            # exist in the archive
                            _ = tar.getmember(dir_component)
                        except KeyError:
                            yield dir_component

                continue

            if dirs_only and not member.isdir():
                continue

            yield member.name

    def _find_base_dir(self, tar, pattern):
        paths = self._list_tar_paths(tar, dirs_only=True)
        matches = sorted(list(utils.glob(paths, pattern)))
        if not matches:
            raise SourceError("{}: Could not find base directory matching pattern: {}".format(self, pattern))

        return matches[0]


def setup():
    return TarSource
