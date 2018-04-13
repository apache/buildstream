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
bzr - stage files from a bazaar repository
==========================================

**Host dependencies:**

  * bzr

**Usage:**

.. code:: yaml

   # Specify the bzr source kind
   kind: bzr

   # Optionally specify a relative staging directory
   # directory: path/to/stage

   # Specify the bzr url. Bazaar URLs come in many forms, see
   # `bzr help urlspec` for more information. Using an alias defined
   # in your project configuration is encouraged.
   url: https://launchpad.net/bzr

   # Specify the tracking branch. This is mandatory, as bzr cannot identify
   # an individual revision outside its branch. bzr URLs that omit the branch
   # name implicitly specify the trunk branch, but bst requires this to be
   # explicit.
   track: trunk

   # Specify the ref. This is a revision number. This is usually a decimal,
   # but revisions on a branch are of the form
   # <revision-branched-from>.<branch-number>.<revision-since-branching>
   # e.g. 6622.1.6.
   # The ref must be specified to build, and 'bst track' will update the
   # revision number to the one on the tip of the branch specified in 'track'.
   ref: 6622

"""

import os
import shutil
from contextlib import contextmanager

from buildstream import Source, SourceError, Consistency
from buildstream import utils


class BzrSource(Source):
    # pylint: disable=attribute-defined-outside-init

    def configure(self, node):
        self.node_validate(node, ['url', 'track', 'ref'] + Source.COMMON_CONFIG_KEYS)

        self.original_url = self.node_get_member(node, str, 'url')
        self.tracking = self.node_get_member(node, str, 'track')
        self.ref = self.node_get_member(node, str, 'ref', None)
        self.url = self.translate_url(self.original_url)

    def preflight(self):
        # Check if bzr is installed, get the binary at the same time.
        self.host_bzr = utils.get_host_tool('bzr')

    def get_unique_key(self):
        return [self.original_url, self.tracking, self.ref]

    def get_consistency(self):
        if self.ref is None or self.tracking is None:
            return Consistency.INCONSISTENT

        if self._check_ref():
            return Consistency.CACHED
        else:
            return Consistency.RESOLVED

    def load_ref(self, node):
        self.ref = self.node_get_member(node, str, 'ref', None)

    def get_ref(self):
        return self.ref

    def set_ref(self, ref, node):
        node['ref'] = self.ref = ref

    def track(self):
        with self.timed_activity("Tracking {}".format(self.url),
                                 silent_nested=True):
            self._ensure_mirror(skip_ref_check=True)
            ret, out = self.check_output([self.host_bzr, "version-info",
                                          "--custom", "--template={revno}",
                                          self._get_branch_dir()],
                                         fail="Failed to read the revision number at '{}'"
                                         .format(self._get_branch_dir()))
            if ret != 0:
                raise SourceError("{}: Failed to get ref for tracking {}".format(self, self.tracking))

            return out

    def fetch(self):
        with self.timed_activity("Fetching {}".format(self.url),
                                 silent_nested=True):
            self._ensure_mirror()

    def stage(self, directory):
        self.call([self.host_bzr, "checkout", "--lightweight",
                   "--revision=revno:{}".format(self.ref),
                   self._get_branch_dir(), directory],
                  fail="Failed to checkout revision {} from branch {} to {}"
                  .format(self.ref, self._get_branch_dir(), directory))

    def init_workspace(self, directory):
        url = os.path.join(self.url, self.tracking)
        with self.timed_activity('Setting up workspace "{}"'.format(directory), silent_nested=True):
            # Checkout from the cache
            self.call([self.host_bzr, "branch",
                       "--use-existing-dir",
                       "--revision=revno:{}".format(self.ref),
                       self._get_branch_dir(), directory],
                      fail="Failed to branch revision {} from branch {} to {}"
                      .format(self.ref, self._get_branch_dir(), directory))
            # Switch the parent branch to the source's origin
            self.call([self.host_bzr, "switch",
                       "--directory={}".format(directory), url],
                      fail="Failed to switch workspace's parent branch to {}".format(url))

    def _check_ref(self):
        # If the mirror doesnt exist yet, then we dont have the ref
        if not os.path.exists(self._get_branch_dir()):
            return False

        return self.call([self.host_bzr, "revno",
                          "--revision=revno:{}".format(self.ref),
                          self._get_branch_dir()]) == 0

    def _get_branch_dir(self):
        return os.path.join(self._get_mirror_dir(), self.tracking)

    def _get_mirror_dir(self):
        return os.path.join(self.get_mirror_directory(),
                            utils.url_directory_name(self.original_url))

    def _atomic_replace_mirrordir(self, srcdir):
        """Helper function to safely replace the mirror dir"""

        if not os.path.exists(self._get_mirror_dir()):
            # Just move the srcdir to the mirror dir
            try:
                os.rename(srcdir, self._get_mirror_dir())
            except OSError as e:
                raise SourceError("{}: Failed to move srcdir '{}' to mirror dir '{}'"
                                  .format(str(self), srcdir, self._get_mirror_dir())) from e
        else:
            # Atomically swap the backup dir.
            backupdir = self._get_mirror_dir() + ".bak"
            try:
                os.rename(self._get_mirror_dir(), backupdir)
            except OSError as e:
                raise SourceError("{}: Failed to move mirrordir '{}' to backup dir '{}'"
                                  .format(str(self), self._get_mirror_dir(), backupdir)) from e

            try:
                os.rename(srcdir, self._get_mirror_dir())
            except OSError as e:
                # Attempt to put the backup back!
                os.rename(backupdir, self._get_mirror_dir())
                raise SourceError("{}: Failed to replace bzr repo '{}' with '{}"
                                  .format(str(self), srcdir, self._get_mirror_dir())) from e
            finally:
                if os.path.exists(backupdir):
                    shutil.rmtree(backupdir)

    @contextmanager
    def _atomic_repodir(self):
        """Context manager for working in a copy of the bzr repository

        Yields:
           (str): A path to the copy of the bzr repo

        This should be used because bzr does not give any guarantees of
        atomicity, and aborting an operation at the wrong time (or
        accidentally running multiple concurrent operations) can leave the
        repo in an inconsistent state.
        """
        with self.tempdir() as repodir:
            mirror_dir = self._get_mirror_dir()
            if os.path.exists(mirror_dir):
                try:
                    # shutil.copytree doesn't like it if destination exists
                    shutil.rmtree(repodir)
                    shutil.copytree(mirror_dir, repodir)
                except (shutil.Error, OSError) as e:
                    raise SourceError("{}: Failed to copy bzr repo from '{}' to '{}'"
                                      .format(str(self), mirror_dir, repodir)) from e

            yield repodir
            self._atomic_replace_mirrordir(repodir)

    def _ensure_mirror(self, skip_ref_check=False):
        with self._atomic_repodir() as repodir:
            # Initialize repo if no metadata
            bzr_metadata_dir = os.path.join(repodir, ".bzr")
            if not os.path.exists(bzr_metadata_dir):
                self.call([self.host_bzr, "init-repo", "--no-trees", repodir],
                          fail="Failed to initialize bzr repository")

            branch_dir = os.path.join(repodir, self.tracking)
            branch_url = self.url + "/" + self.tracking
            if not os.path.exists(branch_dir):
                # `bzr branch` the branch if it doesn't exist
                # to get the upstream code
                self.call([self.host_bzr, "branch", branch_url, branch_dir],
                          fail="Failed to branch from {} to {}".format(branch_url, branch_dir))

            else:
                # `bzr pull` the branch if it does exist
                # to get any changes to the upstream code
                self.call([self.host_bzr, "pull", "--directory={}".format(branch_dir), branch_url],
                          fail="Failed to pull new changes for {}".format(branch_dir))
        if not skip_ref_check and not self._check_ref():
            raise SourceError("Failed to ensure ref '{}' was mirrored".format(self.ref),
                              reason="ref-not-mirrored")


def setup():
    return BzrSource
