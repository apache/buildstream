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

"""
git - stage files from a git repository
=======================================

**Host dependencies:**

  * git

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

   # Optionally specify the ref format used for tracking.
   # The default is 'sha1' for the raw commit hash.
   # If you specify 'git-describe', the commit hash will be prefixed
   # with the closest tag.
   ref-format: sha1

   # Specify the commit ref, this must be specified in order to
   # checkout sources and build, but can be automatically updated
   # if the 'track' attribute was specified.
   ref: d63cbb6fdc0bbdadc4a1b92284826a6d63a7ebcd

   # Optionally specify whether submodules should be checked-out.
   # If not set, this will default to 'True'
   checkout-submodules: True

   # If your repository has submodules, explicitly specifying the
   # url from which they are to be fetched allows you to easily
   # rebuild the same sources from a different location. This is
   # especially handy when used with project defined aliases which
   # can be redefined at a later time.
   # You may also explicitly specify whether to check out this
   # submodule. If 'checkout' is set, it will override
   # 'checkout-submodules' with the value set below.
   submodules:
     plugins/bar:
       url: upstream:bar.git
       checkout: True
     plugins/baz:
       url: upstream:baz.git
       checkout: False

**Configurable Warnings:**

This plugin provides the following :ref:`configurable warnings <configurable_warnings>`:

- ``git:inconsistent-submodule`` - A submodule present in the git repository's .gitmodules was never
  added with `git submodule add`.

- ``git:unlisted-submodule`` - A submodule is present in the git repository but was not specified in
  the source configuration and was not disabled for checkout.

  .. note::

     The ``git:unlisted-submodule`` warning is available since :ref:`format version 20 <project_format_version>`

- ``git:invalid-submodule`` - A submodule is specified in the source configuration but does not exist
  in the repository.

  .. note::

     The ``git:invalid-submodule`` warning is available since :ref:`format version 20 <project_format_version>`

This plugin also utilises the following configurable :class:`core warnings <buildstream.types.CoreWarnings>`:

- :attr:`ref-not-in-track <buildstream.types.CoreWarnings.REF_NOT_IN_TRACK>` - The provided ref was not
  found in the provided track in the element's git repository.
"""

import os
import errno
import re
from collections.abc import Mapping
from io import StringIO

from configparser import RawConfigParser

from buildstream import Source, SourceError, Consistency, SourceFetcher, CoreWarnings
from buildstream import utils

GIT_MODULES = '.gitmodules'

# Warnings
WARN_INCONSISTENT_SUBMODULE = "inconsistent-submodule"
WARN_UNLISTED_SUBMODULE = "unlisted-submodule"
WARN_INVALID_SUBMODULE = "invalid-submodule"


# Because of handling of submodules, we maintain a GitMirror
# for the primary git source and also for each submodule it
# might have at a given time
#
class GitMirror(SourceFetcher):

    def __init__(self, source, path, url, ref, *, primary=False):

        super().__init__()
        self.source = source
        self.path = path
        self.url = url
        self.ref = ref
        self.primary = primary
        self.mirror = os.path.join(source.get_mirror_directory(), utils.url_directory_name(url))
        self.mark_download_url(url)

    # Ensures that the mirror exists
    def ensure(self, alias_override=None):

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
                url = self.source.translate_url(self.url, alias_override=alias_override,
                                                primary=self.primary)
                self.source.call([self.source.host_git, 'clone', '--mirror', '-n', url, tmpdir],
                                 fail="Failed to clone git repository {}".format(url),
                                 fail_temporarily=True)

                # Attempt atomic rename into destination, this will fail if
                # another process beat us to the punch
                try:
                    os.rename(tmpdir, self.mirror)
                except OSError as e:

                    # When renaming and the destination repo already exists, os.rename()
                    # will fail with ENOTEMPTY or EEXIST, since an empty directory will
                    # be silently replaced
                    if e.errno in (errno.ENOTEMPTY, errno.EEXIST):
                        self.source.status("{}: Discarding duplicate clone of {}"
                                           .format(self.source, url))
                    else:
                        raise SourceError("{}: Failed to move cloned git repository {} from '{}' to '{}': {}"
                                          .format(self.source, url, tmpdir, self.mirror, e)) from e

    def _fetch(self, alias_override=None):
        url = self.source.translate_url(self.url,
                                        alias_override=alias_override,
                                        primary=self.primary)

        if alias_override:
            remote_name = utils.url_directory_name(alias_override)
            _, remotes = self.source.check_output(
                [self.source.host_git, 'remote'],
                fail="Failed to retrieve list of remotes in {}".format(self.mirror),
                cwd=self.mirror
            )
            if remote_name not in remotes.strip().split():
                self.source.call(
                    [self.source.host_git, 'remote', 'add', remote_name, url],
                    fail="Failed to add remote {} with url {}".format(remote_name, url),
                    cwd=self.mirror
                )
        else:
            remote_name = "origin"

        # In git < 1.9.0, we have to call `git fetch` twice, once for the tags
        #
        if self.source.git_fetch_tags_exclusive:
            self.source.call([self.source.host_git, 'fetch', remote_name, '--prune', '--force'],
                             fail="Failed to fetch from remote git repository: {}".format(url),
                             fail_temporarily=True,
                             cwd=self.mirror)

        self.source.call([self.source.host_git, 'fetch', remote_name, '--prune', '--force', '--tags'],
                         fail="Failed to fetch from remote git repository: {}".format(url),
                         fail_temporarily=True,
                         cwd=self.mirror)

    def fetch(self, alias_override=None):
        # Resolve the URL for the message
        resolved_url = self.source.translate_url(self.url,
                                                 alias_override=alias_override,
                                                 primary=self.primary)

        with self.source.timed_activity("Fetching from {}"
                                        .format(resolved_url),
                                        silent_nested=True):
            self.ensure(alias_override)
            if not self.has_ref():
                self._fetch(alias_override)
            self.assert_ref()

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
            raise SourceError("{}: expected ref '{}' was not found in git repository: '{}'"
                              .format(self.source, self.ref, self.url))

    def latest_commit(self, tracking):
        _, output = self.source.check_output(
            [self.source.host_git, 'rev-parse', tracking],
            fail="Unable to find commit for specified branch name '{}'".format(tracking),
            cwd=self.mirror)
        ref = output.rstrip('\n')

        if self.source.ref_format == 'git-describe':
            # Prefix the ref with the closest tag, if available,
            # to make the ref human readable
            exit_code, output = self.source.check_output(
                [self.source.host_git, 'describe', '--tags', '--abbrev=40', '--long', ref],
                cwd=self.mirror)
            if exit_code == 0:
                ref = output.rstrip('\n')

        return ref

    def stage(self, directory):
        fullpath = os.path.join(directory, self.path)

        # We need to pass '--no-hardlinks' because there's nothing to
        # stop the build from overwriting the files in the .git directory
        # inside the sandbox.
        self.source.call([self.source.host_git, 'clone', '--no-checkout', '--no-hardlinks', self.mirror, fullpath],
                         fail="Failed to create git mirror {} in directory: {}".format(self.mirror, fullpath),
                         fail_temporarily=True)

        self.source.call([self.source.host_git, 'checkout', '--force', self.ref],
                         fail="Failed to checkout git ref {}".format(self.ref),
                         cwd=fullpath)

    def init_workspace(self, directory):
        fullpath = os.path.join(directory, self.path)
        url = self.source.translate_url(self.url)

        self.source.call([self.source.host_git, 'clone', '--no-checkout', self.mirror, fullpath],
                         fail="Failed to clone git mirror {} in directory: {}".format(self.mirror, fullpath),
                         fail_temporarily=True)

        self.source.call([self.source.host_git, 'remote', 'set-url', 'origin', url],
                         fail='Failed to add remote origin "{}"'.format(url),
                         cwd=fullpath)

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
                    plugin=self, ref=self.ref))

        content = '\n'.join([l.strip() for l in output.splitlines()])

        io = StringIO(content)
        parser = RawConfigParser()
        parser.read_file(io)

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
                raise SourceError("{}: Error reading commit information for submodule '{}'"
                                  .format(self.source, submodule))

            return submodule_commit

        else:
            detail = "The submodule '{}' is defined either in the BuildStream source\n".format(submodule) + \
                     "definition, or in a .gitmodules file. But the submodule was never added to the\n" + \
                     "underlying git repository with `git submodule add`."

            self.source.warn("{}: Ignoring inconsistent submodule '{}'"
                             .format(self.source, submodule), detail=detail, warning_token=WARN_INCONSISTENT_SUBMODULE)

            return None


class GitSource(Source):
    # pylint: disable=attribute-defined-outside-init

    #
    # The --tags option before git 1.9.0 used to mean to fetch tags exclusively,
    # since git 1.9.0 the --tags option means to additionally fetch tags.
    #
    #    https://github.com/git/git/blob/master/Documentation/RelNotes/1.9.0.txt
    #
    git_fetch_tags_exclusive = None

    def configure(self, node):
        ref = self.node_get_member(node, str, 'ref', None)

        config_keys = ['url', 'track', 'ref', 'submodules', 'checkout-submodules', 'ref-format']
        self.node_validate(node, config_keys + Source.COMMON_CONFIG_KEYS)

        self.original_url = self.node_get_member(node, str, 'url')
        self.mirror = GitMirror(self, '', self.original_url, ref, primary=True)
        self.tracking = self.node_get_member(node, str, 'track', None)

        self.ref_format = self.node_get_member(node, str, 'ref-format', 'sha1')
        if self.ref_format not in ['sha1', 'git-describe']:
            provenance = self.node_provenance(node, member_name='ref-format')
            raise SourceError("{}: Unexpected value for ref-format: {}".format(provenance, self.ref_format))

        # At this point we now know if the source has a ref and/or a track.
        # If it is missing both then we will be unable to track or build.
        if self.mirror.ref is None and self.tracking is None:
            raise SourceError("{}: Git sources require a ref and/or track".format(self),
                              reason="missing-track-and-ref")

        self.checkout_submodules = self.node_get_member(node, bool, 'checkout-submodules', True)
        self.submodules = []

        # Parse a dict of submodule overrides, stored in the submodule_overrides
        # and submodule_checkout_overrides dictionaries.
        self.submodule_overrides = {}
        self.submodule_checkout_overrides = {}
        modules = self.node_get_member(node, Mapping, 'submodules', {})
        for path, _ in self.node_items(modules):
            submodule = self.node_get_member(modules, Mapping, path)
            url = self.node_get_member(submodule, str, 'url', None)

            # Make sure to mark all URLs that are specified in the configuration
            if url:
                self.mark_download_url(url, primary=False)

            self.submodule_overrides[path] = url
            if 'checkout' in submodule:
                checkout = self.node_get_member(submodule, bool, 'checkout')
                self.submodule_checkout_overrides[path] = checkout

        self.mark_download_url(self.original_url)

    def preflight(self):
        # Check if git is installed, get the binary at the same time
        self.host_git = utils.get_host_tool('git')

        # Resolve what `--tags` means when calling `git fetch`
        self.init_fetch_tags_mode()

    def get_unique_key(self):
        # Here we want to encode the local name of the repository and
        # the ref, if the user changes the alias to fetch the same sources
        # from another location, it should not effect the cache key.
        key = [self.original_url, self.mirror.ref]

        # Only modify the cache key with checkout_submodules if it's something
        # other than the default behaviour.
        if self.checkout_submodules is False:
            key.append({"checkout_submodules": self.checkout_submodules})

        # We want the cache key to change if the source was
        # configured differently, and submodules count.
        if self.submodule_overrides:
            key.append(self.submodule_overrides)

        if self.submodule_checkout_overrides:
            key.append({"submodule_checkout_overrides": self.submodule_checkout_overrides})

        return key

    def get_consistency(self):
        if self.have_all_refs():
            return Consistency.CACHED
        elif self.mirror.ref is not None:
            return Consistency.RESOLVED
        return Consistency.INCONSISTENT

    def load_ref(self, node):
        self.mirror.ref = self.node_get_member(node, str, 'ref', None)

    def get_ref(self):
        return self.mirror.ref

    def set_ref(self, ref, node):
        node['ref'] = self.mirror.ref = ref

    def track(self):

        # If self.tracking is not specified it's not an error, just silently return
        if not self.tracking:
            return None

        # Resolve the URL for the message
        resolved_url = self.translate_url(self.mirror.url)
        with self.timed_activity("Tracking {} from {}"
                                 .format(self.tracking, resolved_url),
                                 silent_nested=True):
            self.mirror.ensure()
            self.mirror._fetch()

            # Update self.mirror.ref and node.ref from the self.tracking branch
            ret = self.mirror.latest_commit(self.tracking)

        return ret

    def init_workspace(self, directory):
        # XXX: may wish to refactor this as some code dupe with stage()
        self.refresh_submodules()

        with self.timed_activity('Setting up workspace "{}"'.format(directory), silent_nested=True):
            self.mirror.init_workspace(directory)
            for mirror in self.submodules:
                mirror.init_workspace(directory)

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

    def get_source_fetchers(self):
        yield self.mirror
        self.refresh_submodules()
        for submodule in self.submodules:
            yield submodule

    def validate_cache(self):
        discovered_submodules = {}
        unlisted_submodules = []
        invalid_submodules = []

        for path, url in self.mirror.submodule_list():
            discovered_submodules[path] = url
            if self.ignore_submodule(path):
                continue

            override_url = self.submodule_overrides.get(path)
            if not override_url:
                unlisted_submodules.append((path, url))

        # Warn about submodules which are explicitly configured but do not exist
        for path, url in self.submodule_overrides.items():
            if path not in discovered_submodules:
                invalid_submodules.append((path, url))

        if invalid_submodules:
            detail = []
            for path, url in invalid_submodules:
                detail.append("  Submodule URL '{}' at path '{}'".format(url, path))

            self.warn("{}: Invalid submodules specified".format(self),
                      warning_token=WARN_INVALID_SUBMODULE,
                      detail="The following submodules are specified in the source "
                      "description but do not exist according to the repository\n\n" +
                      "\n".join(detail))

        # Warn about submodules which exist but have not been explicitly configured
        if unlisted_submodules:
            detail = []
            for path, url in unlisted_submodules:
                detail.append("  Submodule URL '{}' at path '{}'".format(url, path))

            self.warn("{}: Unlisted submodules exist".format(self),
                      warning_token=WARN_UNLISTED_SUBMODULE,
                      detail="The following submodules exist but are not specified " +
                      "in the source description\n\n" +
                      "\n".join(detail))

        # Assert that the ref exists in the track tag/branch, if track has been specified.
        ref_in_track = False
        if self.tracking:
            _, branch = self.check_output([self.host_git, 'branch', '--list', self.tracking,
                                           '--contains', self.mirror.ref],
                                          cwd=self.mirror.mirror)
            if branch:
                ref_in_track = True
            else:
                _, tag = self.check_output([self.host_git, 'tag', '--list', self.tracking,
                                            '--contains', self.mirror.ref],
                                           cwd=self.mirror.mirror)
                if tag:
                    ref_in_track = True

            if not ref_in_track:
                detail = "The ref provided for the element does not exist locally " + \
                         "in the provided track branch / tag '{}'.\n".format(self.tracking) + \
                         "You may wish to track the element to update the ref from '{}' ".format(self.tracking) + \
                         "with `bst track`,\n" + \
                         "or examine the upstream at '{}' for the specific ref.".format(self.mirror.url)

                self.warn("{}: expected ref '{}' was not found in given track '{}' for staged repository: '{}'\n"
                          .format(self, self.mirror.ref, self.tracking, self.mirror.url),
                          detail=detail, warning_token=CoreWarnings.REF_NOT_IN_TRACK)

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
        self.mirror.ensure()
        submodules = []

        for path, url in self.mirror.submodule_list():

            # Completely ignore submodules which are disabled for checkout
            if self.ignore_submodule(path):
                continue

            # Allow configuration to override the upstream
            # location of the submodules.
            override_url = self.submodule_overrides.get(path)
            if override_url:
                url = override_url

            ref = self.mirror.submodule_ref(path)
            if ref is not None:
                mirror = GitMirror(self, path, url, ref)
                submodules.append(mirror)

        self.submodules = submodules

    # Checks whether the plugin configuration has explicitly
    # configured this submodule to be ignored
    def ignore_submodule(self, path):
        try:
            checkout = self.submodule_checkout_overrides[path]
        except KeyError:
            checkout = self.checkout_submodules

        return not checkout

    # Checks whether the plugin configuration has explicitly
    # configured this submodule to be ignored
    def ignore_submodule(self, path):
        try:
            checkout = self.submodule_checkout_overrides[path]
        except KeyError:
            checkout = self.checkout_submodules

        return not checkout

    # Resolve GitSource.git_fetch_tags_exclusive
    def init_fetch_tags_mode(self):

        if self.git_fetch_tags_exclusive is None:
            _, version_output = self.check_output([self.host_git, '--version'])
            version_output = version_output.strip()

            # Extract the version from "git version {version}" string
            git_version = version_output.rsplit(maxsplit=1)[-1]

            # Parse out the minor and major versions
            git_version_split = git_version.split(".")
            if len(git_version_split) < 3:
                raise SourceError("{}: Failed to parse git version: {}".format(self, version_output))
            git_version_major = int(git_version_split[0])
            git_version_minor = int(git_version_split[1])

            # Resolve whether `git fetch --tags` means to fetch tags exclusively
            if git_version_major == 1 and git_version_minor < 9:
                type(self).git_fetch_tags_exclusive = True
            else:
                type(self).git_fetch_tags_exclusive = False


# Plugin entry point
def setup():
    return GitSource
