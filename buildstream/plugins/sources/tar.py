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

   # Specify the tar url. Using an alias defined in your project configuration
   # is encouraged. 'bst track' will update the sha256sum in 'ref' to the
   # downloaded file's sha256sum.
   url: upstream:foo.tar

   # Specify the ref. It's a sha256sum of the file you download.
   ref: 6c9f6f68a131ec6381da82f2bff978083ed7f4f7991d931bfa767b7965ebc94b

"""

import os
import urllib.request
import urllib.error
import tarfile
import hashlib
import tempfile

from buildstream import Source, SourceError, Consistency
from buildstream import utils


class TarSource(Source):

    def configure(self, node):
        self.original_url = self.node_get_member(node, str, 'url')
        self.ref = self.node_get_member(node, str, 'ref', '') or None
        self.tracking = self.node_get_member(node, str, 'track', '') or None
        self.url = self.get_project().translate_url(self.original_url)

    def preflight(self):
        return

    def get_unique_key(self):
        return [self.original_url, self.ref]

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
                tar.extractall(directory)
        except tarfile.TarError as e:
            raise SourceError("TarError while staging source") from e
        except OSError as e:
            raise SourceError("OSError while staging source") from e

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
                sha256 = self._sha256sum(local_file)
                # Even if the file already exists, move the new file over.
                # In case the old file was corrupted somehow.
                os.rename(local_file, self._get_mirror_file(sha256))

                return sha256
        except urllib.error.URLError as e:
            raise SourceError("URLError while mirroring source") from e
        except OSError as e:
            raise SourceError("OSError while mirroring source") from e

    def _get_mirror_dir(self):
        return os.path.join(self.get_mirror_directory(),
                            utils.url_directory_name(self.original_url))

    def _get_mirror_file(self, sha=None):
        return os.path.join(self._get_mirror_dir(), sha or self.ref)

    def _sha256sum(self, filename):
        h = hashlib.sha256()
        with open(filename, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                h.update(chunk)
        return h.hexdigest()


def setup():
    return TarSource
