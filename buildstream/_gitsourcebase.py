#
#  Copyright (C) 2016 Codethink Limited
#  Copyright (C) 2018 Bloomberg Finance LP
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
#        Chandan Singh <csingh43@bloomberg.net>

"""Abstract base class for source implementations that work with a Git repository"""

import os
import re
import shutil
from collections.abc import Mapping
from io import StringIO
from tempfile import TemporaryFile

from configparser import RawConfigParser

from buildstream import Source, SourceError, Consistency, SourceFetcher, CoreWarnings
from buildstream import utils
from buildstream.utils import move_atomic, DirectoryExistsError

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

    def __init__(self, source, path, url, ref, *, primary=False, tags=[]):

        super().__init__()
        self.source = source
        self.path = path
        self.url = url
        self.ref = ref
        self.tags = tags
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

                try:
                    move_atomic(tmpdir, self.mirror)
                except DirectoryExistsError:
                    # Another process was quicker to download this repository.
                    # Let's discard our own
                    self.source.status("{}: Discarding duplicate clone of {}"
                                       .format(self.source, url))
                except OSError as e:
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
            if remote_name not in remotes:
                self.source.call(
                    [self.source.host_git, 'remote', 'add', remote_name, url],
                    fail="Failed to add remote {} with url {}".format(remote_name, url),
                    cwd=self.mirror
                )
        else:
            remote_name = "origin"

        self.source.call([self.source.host_git, 'fetch', remote_name, '--prune',
                          '+refs/heads/*:refs/heads/*', '+refs/tags/*:refs/tags/*'],
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

    def latest_commit_with_tags(self, tracking, track_tags=False):
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

        if not track_tags:
            return ref, []

        tags = set()
        for options in [[], ['--first-parent'], ['--tags'], ['--tags', '--first-parent']]:
            exit_code, output = self.source.check_output(
                [self.source.host_git, 'describe', '--abbrev=0', ref] + options,
                cwd=self.mirror)
            if exit_code == 0:
                tag = output.strip()
                _, commit_ref = self.source.check_output(
                    [self.source.host_git, 'rev-parse', tag + '^{commit}'],
                    fail="Unable to resolve tag '{}'".format(tag),
                    cwd=self.mirror)
                exit_code = self.source.call(
                    [self.source.host_git, 'cat-file', 'tag', tag],
                    cwd=self.mirror)
                annotated = (exit_code == 0)

                tags.add((tag, commit_ref.strip(), annotated))

        return ref, list(tags)

    def stage(self, directory):
        fullpath = os.path.join(directory, self.path)

        # Using --shared here avoids copying the objects into the checkout, in any
        # case we're just checking out a specific commit and then removing the .git/
        # directory.
        self.source.call([self.source.host_git, 'clone', '--no-checkout', '--shared', self.mirror, fullpath],
                         fail="Failed to create git mirror {} in directory: {}".format(self.mirror, fullpath),
                         fail_temporarily=True)

        self.source.call([self.source.host_git, 'checkout', '--force', self.ref],
                         fail="Failed to checkout git ref {}".format(self.ref),
                         cwd=fullpath)

        # Remove .git dir
        shutil.rmtree(os.path.join(fullpath, ".git"))

        self._rebuild_git(fullpath)

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

    def init_cached_build_workspace(self, directory):
        fullpath = os.path.join(directory, self.path)
        url = self.source.translate_url(self.url)

        self.source.call([self.source.host_git, 'init', fullpath],
                         fail="Failed to init git in directory: {}".format(fullpath),
                         fail_temporarily=True,
                         cwd=fullpath)

        self.source.call([self.source.host_git, 'fetch', self.mirror],
                         fail='Failed to fetch from local mirror "{}"'.format(self.mirror),
                         cwd=fullpath)

        self.source.call([self.source.host_git, 'remote', 'add', 'origin', url],
                         fail='Failed to add remote origin "{}"'.format(url),
                         cwd=fullpath)

        self.source.call([self.source.host_git, 'update-ref', '--no-deref', 'HEAD', self.ref],
                         fail='Failed update HEAD to ref "{}"'.format(self.ref),
                         cwd=fullpath)

        self.source.call([self.source.host_git, 'read-tree', 'HEAD'],
                         fail='Failed to read HEAD into index',
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
                             .format(self.source, submodule), detail=detail,
                             warning_token=WARN_INCONSISTENT_SUBMODULE)

            return None

    def _rebuild_git(self, fullpath):
        if not self.tags:
            return

        with self.source.tempdir() as tmpdir:
            included = set()
            shallow = set()
            for _, commit_ref, _ in self.tags:

                if commit_ref == self.ref:
                    # rev-list does not work in case of same rev
                    shallow.add(self.ref)
                else:
                    _, out = self.source.check_output([self.source.host_git, 'rev-list',
                                                       '--ancestry-path', '--boundary',
                                                       '{}..{}'.format(commit_ref, self.ref)],
                                                      fail="Failed to get git history {}..{} in directory: {}"
                                                      .format(commit_ref, self.ref, fullpath),
                                                      fail_temporarily=True,
                                                      cwd=self.mirror)
                    self.source.warn("refs {}..{}: {}".format(commit_ref, self.ref, out.splitlines()))
                    for line in out.splitlines():
                        rev = line.lstrip('-')
                        if line[0] == '-':
                            shallow.add(rev)
                        else:
                            included.add(rev)

            shallow -= included
            included |= shallow

            self.source.call([self.source.host_git, 'init'],
                             fail="Cannot initialize git repository: {}".format(fullpath),
                             cwd=fullpath)

            for rev in included:
                with TemporaryFile(dir=tmpdir) as commit_file:
                    self.source.call([self.source.host_git, 'cat-file', 'commit', rev],
                                     stdout=commit_file,
                                     fail="Failed to get commit {}".format(rev),
                                     cwd=self.mirror)
                    commit_file.seek(0, 0)
                    self.source.call([self.source.host_git, 'hash-object', '-w', '-t', 'commit', '--stdin'],
                                     stdin=commit_file,
                                     fail="Failed to add commit object {}".format(rev),
                                     cwd=fullpath)

            with open(os.path.join(fullpath, '.git', 'shallow'), 'w') as shallow_file:
                for rev in shallow:
                    shallow_file.write('{}\n'.format(rev))

            for tag, commit_ref, annotated in self.tags:
                if annotated:
                    with TemporaryFile(dir=tmpdir) as tag_file:
                        tag_data = 'object {}\ntype commit\ntag {}\n'.format(commit_ref, tag)
                        tag_file.write(tag_data.encode('ascii'))
                        tag_file.seek(0, 0)
                        _, tag_ref = self.source.check_output(
                            [self.source.host_git, 'hash-object', '-w', '-t',
                             'tag', '--stdin'],
                            stdin=tag_file,
                            fail="Failed to add tag object {}".format(tag),
                            cwd=fullpath)

                    self.source.call([self.source.host_git, 'tag', tag, tag_ref.strip()],
                                     fail="Failed to tag: {}".format(tag),
                                     cwd=fullpath)
                else:
                    self.source.call([self.source.host_git, 'tag', tag, commit_ref],
                                     fail="Failed to tag: {}".format(tag),
                                     cwd=fullpath)

            with open(os.path.join(fullpath, '.git', 'HEAD'), 'w') as head:
                self.source.call([self.source.host_git, 'rev-parse', self.ref],
                                 stdout=head,
                                 fail="Failed to parse commit {}".format(self.ref),
                                 cwd=self.mirror)


class _GitSourceBase(Source):
    # pylint: disable=attribute-defined-outside-init

    def configure(self, node):
        ref = self.node_get_member(node, str, 'ref', None)

        config_keys = ['url', 'track', 'ref', 'submodules',
                       'checkout-submodules', 'ref-format',
                       'track-tags', 'tags']
        self.node_validate(node, config_keys + Source.COMMON_CONFIG_KEYS)

        tags_node = self.node_get_member(node, list, 'tags', [])
        for tag_node in tags_node:
            self.node_validate(tag_node, ['tag', 'commit', 'annotated'])

        tags = self._load_tags(node)
        self.track_tags = self.node_get_member(node, bool, 'track-tags', False)

        self.original_url = self.node_get_member(node, str, 'url')
        self.mirror = GitMirror(self, '', self.original_url, ref, tags=tags, primary=True)
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

    def get_unique_key(self):
        # Here we want to encode the local name of the repository and
        # the ref, if the user changes the alias to fetch the same sources
        # from another location, it should not affect the cache key.
        key = [self.original_url, self.mirror.ref]
        if self.mirror.tags:
            tags = {tag: (commit, annotated) for tag, commit, annotated in self.mirror.tags}
            key.append({'tags': tags})

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
        if self._have_all_refs():
            return Consistency.CACHED
        elif self.mirror.ref is not None:
            return Consistency.RESOLVED
        return Consistency.INCONSISTENT

    def load_ref(self, node):
        self.mirror.ref = self.node_get_member(node, str, 'ref', None)
        self.mirror.tags = self._load_tags(node)

    def get_ref(self):
        return self.mirror.ref, self.mirror.tags

    def set_ref(self, ref_data, node):
        if not ref_data:
            self.mirror.ref = None
            if 'ref' in node:
                del node['ref']
            self.mirror.tags = []
            if 'tags' in node:
                del node['tags']
        else:
            ref, tags = ref_data
            node['ref'] = self.mirror.ref = ref
            self.mirror.tags = tags
            if tags:
                node['tags'] = []
                for tag, commit_ref, annotated in tags:
                    data = {'tag': tag,
                            'commit': commit_ref,
                            'annotated': annotated}
                    node['tags'].append(data)
            else:
                if 'tags' in node:
                    del node['tags']

    def track(self):

        # If self.tracking is not specified it's not an error, just silently return
        if not self.tracking:
            # Is there a better way to check if a ref is given.
            if self.mirror.ref is None:
                detail = 'Without a tracking branch ref can not be updated. Please ' + \
                         'provide a ref or a track.'
                raise SourceError("{}: No track or ref".format(self),
                                  detail=detail, reason="track-attempt-no-track")
            return None

        # Resolve the URL for the message
        resolved_url = self.translate_url(self.mirror.url)
        with self.timed_activity("Tracking {} from {}"
                                 .format(self.tracking, resolved_url),
                                 silent_nested=True):
            self.mirror.ensure()
            self.mirror._fetch()

            # Update self.mirror.ref and node.ref from the self.tracking branch
            ret = self.mirror.latest_commit_with_tags(self.tracking, self.track_tags)

        return ret

    def init_workspace(self, directory):
        # XXX: may wish to refactor this as some code dupe with stage()
        self._refresh_submodules()

        with self.timed_activity('Setting up workspace "{}"'.format(directory), silent_nested=True):
            self.mirror.init_workspace(directory)
            for mirror in self.submodules:
                mirror.init_workspace(directory)

    def init_cached_build_workspace(self, directory):
        self._refresh_submodules()

        with self.timed_activity('Setting up workspace "{}"'.format(directory), silent_nested=True):
            self.mirror.init_cached_build_workspace(directory)
            for mirror in self.submodules:
                mirror.init_cached_build_workspace(directory)

    def stage(self, directory):

        # Need to refresh submodule list here again, because
        # it's possible that we did not load in the main process
        # with submodules present (source needed fetching) and
        # we may not know about the submodule yet come time to build.
        #
        self._refresh_submodules()

        # Stage the main repo in the specified directory
        #
        with self.timed_activity("Staging {}".format(self.mirror.url), silent_nested=True):
            self.mirror.stage(directory)
            for mirror in self.submodules:
                mirror.stage(directory)

    def get_source_fetchers(self):
        yield self.mirror
        self._refresh_submodules()
        for submodule in self.submodules:
            yield submodule

    def validate_cache(self):
        discovered_submodules = {}
        unlisted_submodules = []
        invalid_submodules = []

        for path, url in self.mirror.submodule_list():
            discovered_submodules[path] = url
            if self._ignore_submodule(path):
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
                         "with `bst source track`,\n" + \
                         "or examine the upstream at '{}' for the specific ref.".format(self.mirror.url)

                self.warn("{}: expected ref '{}' was not found in given track '{}' for staged repository: '{}'\n"
                          .format(self, self.mirror.ref, self.tracking, self.mirror.url),
                          detail=detail, warning_token=CoreWarnings.REF_NOT_IN_TRACK)

    ###########################################################
    #                     Local Functions                     #
    ###########################################################

    def _have_all_refs(self):
        if not self.mirror.has_ref():
            return False

        self._refresh_submodules()
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
    def _refresh_submodules(self):
        self.mirror.ensure()
        submodules = []

        for path, url in self.mirror.submodule_list():

            # Completely ignore submodules which are disabled for checkout
            if self._ignore_submodule(path):
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

    def _load_tags(self, node):
        tags = []
        tags_node = self.node_get_member(node, list, 'tags', [])
        for tag_node in tags_node:
            tag = self.node_get_member(tag_node, str, 'tag')
            commit_ref = self.node_get_member(tag_node, str, 'commit')
            annotated = self.node_get_member(tag_node, bool, 'annotated')
            tags.append((tag, commit_ref, annotated))
        return tags

    # Checks whether the plugin configuration has explicitly
    # configured this submodule to be ignored
    def _ignore_submodule(self, path):
        try:
            checkout = self.submodule_checkout_overrides[path]
        except KeyError:
            checkout = self.checkout_submodules

        return not checkout
