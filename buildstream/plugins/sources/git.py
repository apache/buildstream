#!/usr/bin/env python3
#
#  Copyright (C) 2016 Codethink Limited
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

"""A Source implementation for staging git checkouts

**Usage:**

.. code:: yaml

   # Specify the git source kind
   kind: git

   # Optionally specify a relative staging directory
   # directory: path/to/stage

   # Specify the repository url, using an alias defined
   # in your project configuration is recommended.
   url: upstream:foo.git

   # Optionally specify a symbolic tracking branch or tag, this
   # will be used to update the 'ref' when refreshing the pipeline.
   track: master

   # Specify the commit ref, this must be specified in order to
   # checkout sources and build, but can be automatically updated
   # if the 'track' attribute was specified.
   ref: d63cbb6fdc0bbdadc4a1b92284826a6d63a7ebcd
"""

import os
import subprocess
import tempfile
import shutil

from buildstream import Source, SourceError
from buildstream import utils


class GitSource(Source):

    def configure(self, node):
        project = self.get_project()

        self.url = utils.node_get_member(node, str, 'url')
        self.full_url = project.translate_url(self.url)
        self.ref = utils.node_get_member(node, str, 'ref', '')
        self.track = utils.node_get_member(node, str, 'track', '')

        self.mirror = os.path.join(self.get_mirror_directory(), utils.url_directory_name(self.full_url))

    def preflight(self):
        # Check if git is installed, get the binary at the same time
        self.host_git = utils.get_host_tool('git')

    def get_unique_key(self):
        # Here we want to encode the local name of the repository and
        # the ref, if the user changes the alias to fetch the same sources
        # from another location, it should not effect the cache key.
        return [self.url, self.ref]

    def refresh(self, node):
        # If self.track is not specified it's not an error, just silently return
        if not self.track:
            return

        # Update self.ref and node.ref from the self.track branch
        self.ensure_mirror()
        self.fetch_refspec(self.track)
        node['ref'] = self.ref = self.ref_from_track()

    def fetch(self):
        # Here we are only interested in ensuring that our mirror contains
        # the self.ref commit.
        self.ensure_mirror()
        if not self.mirror_has_ref(self.ref):
            self.fetch_refspec(self.ref)

    def stage(self, directory):
        # Checkout self.ref into the specified directory
        #
        with open(os.devnull, "w") as fnull:
            # We need to pass '--no-hardlinks' because there's nothing to
            # stop the build from overwriting the files in the .git directory
            # inside the sandbox.
            if subprocess.call([self.host_git, 'clone', '--no-hardlinks', self.mirror, directory],
                               stdout=fnull, stderr=fnull):
                raise SourceError("%s: Failed to checkout git mirror '%s' in directory: %s" %
                                  (str(self), self.mirror, directory))

            if subprocess.call([self.host_git, 'checkout', '--force', self.ref],
                               cwd=directory, stdout=fnull, stderr=fnull):
                raise SourceError("%s: Failed to checkout git ref '%s'" % (str(self), self.ref))

    ###########################################################
    #                     Local Functions                     #
    ###########################################################
    def ensure_mirror(self):
        # Unfortunately, git does not know how to only clone just a specific ref,
        # so we have to download all of those gigs even if we only need a couple
        # of bytes.
        if not os.path.exists(self.mirror):

            # Do the initial clone in a tmpdir just because we want an atomic move
            # after a long standing clone which could fail overtime, for now do
            # this directly in our git directory, eliminating the chances that the
            # system configured tmpdir is not on the same partition.
            #
            tmpdir = tempfile.mkdtemp(dir=self.get_mirror_directory())

            # XXX stdout/stderr should be propagated to the calling pipeline
            if subprocess.call([self.host_git, 'clone', '--mirror', '-n', self.full_url, tmpdir]):

                # We failed, remove the tmpdir now
                shutil.rmtree(tmpdir, ignore_errors=True)
                raise SourceError("%s: Failed to clone git repository %s" % (str(self), self.full_url))

            try:
                shutil.move(tmpdir, self.mirror)
            except (shutil.Error, OSError) as e:
                raise SourceError("%s: Failed to move cloned git repository %s from '%s' to '%s'" %
                                  (str(self), self.full_url, tmpdir, self.mirror)) from e

    def mirror_has_ref(self, ref):
        with open(os.devnull, "w") as fnull:
            out = subprocess.call([self.host_git, 'cat-file', '-t', ref],
                                  cwd=self.mirror, stdout=fnull, stderr=fnull)
            return out == 0

    def fetch_refspec(self, refspec):
        with open(os.devnull, "w") as fnull:
            # XXX stdout/stderr should be propagated to the calling pipeline
            if subprocess.call([self.host_git, 'fetch', 'origin', refspec],
                               cwd=self.mirror, stdout=fnull, stderr=fnull):
                raise SourceError("%s: Failed to fetch '%s' from remote git repository: '%s'" %
                                  (str(self), refspec, self.url))

    def ref_from_track(self):
        with open(os.devnull, "w") as fnull:
            # Program output is returned as 'bytes', but we want plain strings,
            # which for us is utf8
            output = subprocess.check_output([self.host_git, 'rev-parse', self.track],
                                             cwd=self.mirror, stderr=fnull)
            output = output.decode('UTF-8')
            return output.rstrip('\n')


# Plugin entry point
def setup():
    return GitSource
