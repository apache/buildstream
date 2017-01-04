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

   # If your repository has submodules, explicitly specifying the
   # url from which they are to be fetched allows you to easily
   # rebuild the same sources from a different location. This is
   # especially handy when used with project defined aliases which
   # can be redefined at a later time.
   submodules:
     plugins/bar:
       url: upstream:bar.git
     plugins/baz:
       url: upstream:baz.git

"""

import os
import subprocess
import tempfile
import shutil
import re

from subprocess import CalledProcessError
from configparser import RawConfigParser
from io import StringIO

from buildstream import Source, SourceError
from buildstream import utils

GIT_MODULES = '.gitmodules'


# Because of handling of submodules, we maintain a GitMirror
# for the primary git source and also for each submodule it
# might have at a given time
#
class GitMirror():

    def __init__(self, source, path, url, ref):

        project = source.get_project()
        self.source = source
        self.path = path
        self.url = project.translate_url(url)
        self.ref = ref
        self.mirror = os.path.join(source.get_mirror_directory(), utils.url_directory_name(self.url))

    # Ensures that the mirror exists
    def ensure(self):

        # Unfortunately, git does not know how to only clone just a specific ref,
        # so we have to download all of those gigs even if we only need a couple
        # of bytes.
        if not os.path.exists(self.mirror):

            # Do the initial clone in a tmpdir just because we want an atomic move
            # after a long standing clone which could fail overtime, for now do
            # this directly in our git directory, eliminating the chances that the
            # system configured tmpdir is not on the same partition.
            #
            tmpdir = tempfile.mkdtemp(dir=self.source.get_mirror_directory())

            # XXX stdout/stderr should be propagated to the calling pipeline
            if subprocess.call([self.source.host_git, 'clone', '--mirror', '-n', self.url, tmpdir]):

                # We failed, remove the tmpdir now
                shutil.rmtree(tmpdir, ignore_errors=True)
                raise SourceError("%s: Failed to clone git repository %s" % (str(self.source), self.url))

            try:
                shutil.move(tmpdir, self.mirror)
            except (shutil.Error, OSError) as e:
                raise SourceError("%s: Failed to move cloned git repository %s from '%s' to '%s'" %
                                  (str(self.source), self.url, tmpdir, self.mirror)) from e

    def fetch(self):
        with open(os.devnull, "w") as fnull:
            # XXX stdout/stderr should be propagated to the calling pipeline
            if subprocess.call([self.source.host_git, 'fetch', 'origin'],
                               cwd=self.mirror, stdout=fnull, stderr=fnull):
                raise SourceError("%s: Failed to fetch from remote git repository: '%s'" %
                                  (str(self.source), self.url))

        # It is an error if the expected ref is not found in the mirror
        if not self.has_ref():
            raise SourceError("%s: expected ref '%s' was not found in git repository: '%s'" %
                              (str(self.source), self.ref, self.url))

    def has_ref(self):
        with open(os.devnull, "w") as fnull:
            out = subprocess.call([self.source.host_git, 'cat-file', '-t', self.ref],
                                  cwd=self.mirror, stdout=fnull, stderr=fnull)
            return out == 0

    def latest_commit(self, tracking):
        with open(os.devnull, "w") as fnull:
            output = subprocess.check_output([self.source.host_git, 'rev-parse', tracking],
                                             cwd=self.mirror, stderr=fnull)

            # Program output is returned as 'bytes', but we want plain strings,
            # which for us is utf8
            output = output.decode('UTF-8')
            return output.rstrip('\n')

    def stage(self, directory):
        fullpath = os.path.join(directory, self.path)

        # Checkout self.ref into the specified directory
        #
        with open(os.devnull, "w") as fnull:
            # We need to pass '--no-hardlinks' because there's nothing to
            # stop the build from overwriting the files in the .git directory
            # inside the sandbox.
            if subprocess.call([self.source.host_git, 'clone', '--no-hardlinks', self.mirror, fullpath],
                               stdout=fnull, stderr=fnull):
                raise SourceError("%s: Failed to checkout git mirror '%s' in directory: %s" %
                                  (str(self.source), self.mirror, fullpath))

            if subprocess.call([self.source.host_git, 'checkout', '--force', self.ref],
                               cwd=fullpath, stdout=fnull, stderr=fnull):
                raise SourceError("%s: Failed to checkout git ref '%s'" % (str(self.source), self.ref))

    # List the submodules (path/url tuples) present at the given ref of this repo
    def submodule_list(self):
        modules = "%s:%s" % (self.ref, GIT_MODULES)

        with open(os.devnull, "w") as fnull:
            try:
                output = subprocess.check_output([self.source.host_git, 'show', modules],
                                                 cwd=self.mirror, stderr=fnull)
            except CalledProcessError as e:
                # If git show reports error code 128 here, we take it to mean there is
                # no .gitmodules file to display for the given revision.
                if e.returncode == 128:
                    return
                raise e

        output = output.decode('UTF-8')
        content = '\n'.join([l.strip() for l in output.splitlines()])

        io = StringIO(content)
        parser = RawConfigParser()
        parser.readfp(io)

        for section in parser.sections():
            # validate section name against the 'submodule "foo"' pattern
            if re.match(r'submodule "(.*)"', section):
                path = parser.get(section, 'path')
                url = parser.get(section, 'url')

                yield (path, url)

    # Fetch the ref which this mirror requires it's submodule to have,
    # at the given ref of this mirror.
    def submodule_ref(self, submodule):

        # list objects in the parent repo tree to find the commit
        # object that corresponds to the submodule
        with open(os.devnull, "w") as fnull:
            output = subprocess.check_output([self.source.host_git, 'ls-tree', self.ref, submodule],
                                             cwd=self.mirror, stderr=fnull)

        output = output.decode('UTF-8')

        # read the commit hash from the output
        fields = output.split()
        if len(fields) >= 2 and fields[1] == 'commit':
            submodule_commit = output.split()[2]

            # fail if the commit hash is invalid
            if len(submodule_commit) != 40:
                raise SourceError("%s: Error reading commit information for submodule '%s'" %
                                  (str(self.source), submodule))

            return submodule_commit

        else:
            raise SourceError("%s: Failed to read commit information for submodule '%s'" %
                              (str(self.source), submodule))


class GitSource(Source):

    def configure(self, node):
        project = self.get_project()

        ref = utils.node_get_member(node, str, 'ref', '')

        self.original_url = utils.node_get_member(node, str, 'url')
        self.mirror = GitMirror(self, '', self.original_url, ref)
        self.track = utils.node_get_member(node, str, 'track', '')
        self.submodules = []

        # Parse a list of path/uri tuples for the submodule overrides dictionary
        self.submodule_overrides = {}
        modules = utils.node_get_member(node, dict, 'submodules', {})
        for path, _ in utils.node_items(modules):
            submodule = utils.node_get_member(modules, dict, path)
            self.submodule_overrides['path'] = utils.node_get_member(submodule, str, 'url')

    def preflight(self):
        # Check if git is installed, get the binary at the same time
        self.host_git = utils.get_host_tool('git')

    def get_unique_key(self):
        # Here we want to encode the local name of the repository and
        # the ref, if the user changes the alias to fetch the same sources
        # from another location, it should not effect the cache key.
        return [self.original_url, self.mirror.ref]

    def refresh(self, node):
        # If self.track is not specified it's not an error, just silently return
        if not self.track:
            return

        # Update self.mirror.ref and node.ref from the self.track branch
        self.mirror.ensure()
        self.mirror.fetch()
        node['ref'] = self.mirror.ref = self.mirror.latest_commit(self.track)

        # After refreshing we may have a new ref, so we need to ensure
        # that we've cached the desired refs in our mirrors of submodules.
        #
        self.refresh_submodules()
        self.fetch_submodules()

    def fetch(self):
        # Here we are only interested in ensuring that our mirror contains
        # the self.mirror.ref commit.
        self.mirror.ensure()
        if not self.mirror.has_ref():
            self.mirror.fetch()

        # Here after performing any fetches, we need to also ensure that
        # we've cached the desired refs in our mirrors of submodules.
        #
        self.refresh_submodules()
        self.fetch_submodules()

    def stage(self, directory):

        # Stage the main repo in the specified directory
        #
        self.mirror.stage(directory)
        for mirror in self.submodules:
            mirror.stage(directory)

    ###########################################################
    #                     Local Functions                     #
    ###########################################################

    # Refreshes the GitMirror objects for submodules
    #
    # Assumes that we have our mirror and we have the ref which we point to
    #
    def refresh_submodules(self):
        submodules = []
        project = self.get_project()

        # XXX Here we should issue a warning if either:
        #   A.) A submodule exists but is not defined in the element configuration
        #   B.) The element configuration configures submodules which dont exist at the current ref
        #
        for path, url in self.mirror.submodule_list():

            # Allow configuration to override the upstream
            # location of the submodules.
            override_url = self.submodule_overrides.get(path)
            if override_url:
                url = override_url

            ref = self.mirror.submodule_ref(path)
            mirror = GitMirror(self, path, url, ref)
            submodules.append(mirror)

        self.submodules = submodules

    # Ensures that we have mirrored git repositories for all
    # the submodules existing at the given commit of the main git source.
    #
    # Also ensure that these mirrors have the required commits
    # referred to at the given commit of the main git source.
    #
    def fetch_submodules(self):
        for mirror in self.submodules:
            mirror.ensure()
            if not mirror.has_ref():
                mirror.fetch()


# Plugin entry point
def setup():
    return GitSource
