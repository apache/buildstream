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
import tempfile
import shutil
import re
from collections import Mapping
from configparser import RawConfigParser
from io import StringIO

from buildstream import Source, SourceError, Consistency
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
            with self.source.tempdir() as tmpdir:
                self.source.call([self.source.host_git, 'clone', '--mirror', '-n', self.url, tmpdir],
                                 fail="Failed to clone git repository {}".format(self.url))

                try:
                    shutil.move(tmpdir, self.mirror)
                except (shutil.Error, OSError) as e:
                    raise SourceError("%s: Failed to move cloned git repository %s from '%s' to '%s'" %
                                      (str(self.source), self.url, tmpdir, self.mirror)) from e

    def fetch(self):
        self.source.call([self.source.host_git, 'fetch', 'origin'],
                         fail="Failed to fetch from remote git repository: {}".format(self.url),
                         cwd=self.mirror)

    def has_ref(self):
        if not self.ref:
            return False

        # If the mirror doesnt exist, we also dont have the ref
        if not os.path.exists(self.mirror):
            return False

        # Check if the ref is really there
        rc = self.source.call([self.source.host_git, 'cat-file', '-t', self.ref], cwd=self.mirror)
        return rc == 0

    def assert_ref(self):
        if not self.has_ref():
            raise SourceError("%s: expected ref '%s' was not found in git repository: '%s'" %
                              (str(self.source), self.ref, self.url))

    def latest_commit(self, tracking):
        _, output = self.source.check_output(
            [self.source.host_git, 'rev-parse', tracking],
            fail="Unable to find commit for specified branch name '{}'".format(tracking),
            cwd=self.mirror)
        return output.rstrip('\n')

    def stage(self, directory):
        fullpath = os.path.join(directory, self.path)

        # We need to pass '--no-hardlinks' because there's nothing to
        # stop the build from overwriting the files in the .git directory
        # inside the sandbox.
        self.source.call([self.source.host_git, 'clone', '--no-hardlinks', self.mirror, fullpath],
                         fail="Failed to checkout git mirror {} in directory: {}".format(self.mirror, fullpath))

        self.source.call([self.source.host_git, 'checkout', '--force', self.ref],
                         fail="Failed to checkout git ref {}".format(self.ref),
                         cwd=fullpath)

    # List the submodules (path/url tuples) present at the given ref of this repo
    def submodule_list(self):
        modules = "{}:{}".format(self.ref, GIT_MODULES)
        exit_code, output = self.source.check_output(
            [self.source.host_git, 'show', modules], cwd=self.mirror)

        # If git show reports error code 128 here, we take it to mean there is
        # no .gitmodules file to display for the given revision.
        if exit_code == 128:
            return
        elif exit_code != 0:
            raise SourceError(
                "{plugin}: Failed to show gitmodules at ref {ref}".format(
                    plugin=self, ref=self.ref)) from e

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

    # Fetch the ref which this mirror requires its submodule to have,
    # at the given ref of this mirror.
    def submodule_ref(self, submodule, ref=None):
        if not ref:
            ref = self.ref

        # list objects in the parent repo tree to find the commit
        # object that corresponds to the submodule
        _, output = self.source.check_output([self.source.host_git, 'ls-tree', ref, submodule],
                                             fail="ls-tree failed for commit {} and submodule: {}".format(
                                                 ref, submodule),
                                             cwd=self.mirror)

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
        ref = self.node_get_member(node, str, 'ref', '') or None

        self.original_url = self.node_get_member(node, str, 'url')
        self.mirror = GitMirror(self, '', self.original_url, ref)
        self.tracking = self.node_get_member(node, str, 'track', '') or None
        self.submodules = []

        # Parse a list of path/uri tuples for the submodule overrides dictionary
        self.submodule_overrides = {}
        modules = self.node_get_member(node, Mapping, 'submodules', {})
        for path, _ in self.node_items(modules):
            submodule = self.node_get_member(modules, Mapping, path)
            self.submodule_overrides[path] = self.node_get_member(submodule, str, 'url')

        if not (ref or self.tracking):
            raise SourceError("Must specify either 'ref' or 'track' parameters")

    def preflight(self):
        # Check if git is installed, get the binary at the same time
        self.host_git = utils.get_host_tool('git')

    def get_unique_key(self):
        # Here we want to encode the local name of the repository and
        # the ref, if the user changes the alias to fetch the same sources
        # from another location, it should not effect the cache key.
        return [self.original_url, self.mirror.ref]

    def get_consistency(self):
        if self.have_all_refs():
            return Consistency.CACHED
        elif self.mirror.ref is not None:
            return Consistency.RESOLVED
        return Consistency.INCONSISTENT

    def get_ref(self):
        return self.mirror.ref

    def set_ref(self, ref, node):
        node['ref'] = self.mirror.ref = ref

    def track(self):

        # If self.tracking is not specified it's not an error, just silently return
        if not self.tracking:
            return None

        with self.timed_activity("Tracking {} from {}"
                                 .format(self.tracking, self.mirror.url),
                                 silent_nested=True):
            self.mirror.ensure()
            self.mirror.fetch()

            # Update self.mirror.ref and node.ref from the self.tracking branch
            ret = self.mirror.latest_commit(self.tracking)

        return ret

    def fetch(self):

        with self.timed_activity("Fetching {}".format(self.mirror.url), silent_nested=True):

            # Here we are only interested in ensuring that our mirror contains
            # the self.mirror.ref commit.
            self.mirror.ensure()
            if not self.mirror.has_ref():
                self.mirror.fetch()

            self.mirror.assert_ref()

            # Here after performing any fetches, we need to also ensure that
            # we've cached the desired refs in our mirrors of submodules.
            #
            self.refresh_submodules()
            self.fetch_submodules()

    def stage(self, directory):

        # Need to refresh submodule list here again, because
        # it's possible that we did not load in the main process
        # with submodules present (source needed fetching) and
        # we may not know about the submodule yet come time to build.
        #
        self.refresh_submodules()

        # Stage the main repo in the specified directory
        #
        with self.timed_activity("Staging {}".format(self.mirror.url), silent_nested=True):
            self.mirror.stage(directory)
            for mirror in self.submodules:
                mirror.stage(directory)

    ###########################################################
    #                     Local Functions                     #
    ###########################################################
    def have_all_refs(self):
        if not self.mirror.has_ref():
            return False

        self.refresh_submodules()
        for mirror in self.submodules:
            if not os.path.exists(mirror.mirror):
                return False
            if not mirror.has_ref():
                return False

        return True

    # Refreshes the GitMirror objects for submodules
    #
    # Assumes that we have our mirror and we have the ref which we point to
    #
    def refresh_submodules(self):
        submodules = []

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
                mirror.assert_ref()


# Plugin entry point
def setup():
    return GitSource
