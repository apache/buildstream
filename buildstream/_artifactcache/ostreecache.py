#!/usr/bin/env python3
#
#  Copyright (C) 2017-2018 Codethink Limited
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
#        Jürg Billeter <juerg.billeter@codethink.co.uk>

import multiprocessing
import os
import signal
import tempfile

from .. import _ostree, _signals, utils
from .._exceptions import ArtifactError
from .._ostree import OSTreeError

from . import ArtifactCache
from .pushreceive import initialize_push_connection
from .pushreceive import push as push_artifact
from .pushreceive import PushException


# An OSTreeCache manages artifacts in an OSTree repository
#
# Args:
#     context (Context): The BuildStream context
#     project (Project): The BuildStream project
#     enable_push (bool): Whether pushing is allowed by the platform
#
# Pushing is explicitly disabled by the platform in some cases,
# like when we are falling back to functioning without using
# user namespaces.
#
class OSTreeCache(ArtifactCache):

    def __init__(self, context, *, enable_push):
        super().__init__(context)

        self.enable_push = enable_push

        ostreedir = os.path.join(context.artifactdir, 'ostree')
        self.repo = _ostree.ensure(ostreedir, False)

        # Per-project list of OSTreeRemote and OSTreeArtifactMap instances.
        self._remotes = {}
        self._artifact_maps = {}

        self._has_fetch_remotes = False
        self._has_push_remotes = False

        # A cached artifact cache size (irony?)
        self.__cache_size = None

    ################################################
    #     Implementation of abstract methods       #
    ################################################
    def has_fetch_remotes(self):
        return self._has_fetch_remotes

    def has_push_remotes(self, *, element=None):
        if not self._has_push_remotes:
            # No project has push remotes
            return False
        elif element is None:
            # At least one (sub)project has push remotes
            return True
        else:
            # Check whether the specified element's project has push remotes
            remotes_for_project = self._remotes[element._get_project()]
            return any(remote.spec.push for remote in remotes_for_project)

    def contains(self, element, key):
        ref = self.get_artifact_fullname(element, key)
        return _ostree.exists(self.repo, ref)

    def remote_contains(self, element, key):
        remotes = self._remotes_containing_key(element, key)
        return len(remotes) > 0

    def push_needed(self, element, key):

        remotes_with_artifact = self._remotes_containing_key(element, key)

        push_remotes_with_artifact = set(r for r in remotes_with_artifact if r.spec.push)
        push_remotes_for_project = set(self._remotes[element._get_project()])
        return not push_remotes_for_project.issubset(push_remotes_with_artifact)

    def remove(self, ref):
        return _ostree.remove(self.repo, ref)

    def extract(self, element, key):
        ref = self.get_artifact_fullname(element, key)

        # resolve ref to checksum
        rev = _ostree.checksum(self.repo, ref)

        if not rev:
            raise ArtifactError("Artifact missing for {}".format(ref))

        dest = os.path.join(self.extractdir, element._get_project().name, element.normal_name, rev)
        if os.path.isdir(dest):
            # artifact has already been extracted
            return dest

        os.makedirs(self.extractdir, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='tmp', dir=self.extractdir) as tmpdir:

            checkoutdir = os.path.join(tmpdir, ref)

            _ostree.checkout(self.repo, checkoutdir, rev, user=True)

            os.makedirs(os.path.dirname(dest), exist_ok=True)
            try:
                os.rename(checkoutdir, dest)
            except OSError as e:
                # With rename, it's possible to get either ENOTEMPTY or EEXIST
                # in the case that the destination path is a not empty directory.
                #
                # If rename fails with these errors, another process beat
                # us to it so just ignore.
                if e.errno not in [os.errno.ENOTEMPTY, os.errno.EEXIST]:
                    raise ArtifactError("Failed to extract artifact for ref '{}': {}"
                                        .format(ref, e)) from e

        return dest

    def commit(self, element, content, keys):
        refs = [self.get_artifact_fullname(element, key) for key in keys]

        try:
            _ostree.commit(self.repo, content, refs)
        except OSTreeError as e:
            raise ArtifactError("Failed to commit artifact: {}".format(e)) from e

        self.__cache_size = None

    def can_diff(self):
        return True

    def diff(self, element, key_a, key_b, *, subdir=None):
        _, a, _ = self.repo.read_commit(self.get_artifact_fullname(element, key_a))
        _, b, _ = self.repo.read_commit(self.get_artifact_fullname(element, key_b))

        if subdir:
            a = a.get_child(subdir)
            b = b.get_child(subdir)

            subpath = a.get_path()
        else:
            subpath = '/'

        modified, removed, added = _ostree.diff_dirs(a, b)

        modified = [os.path.relpath(item.target.get_path(), subpath) for item in modified]
        removed = [os.path.relpath(item.get_path(), subpath) for item in removed]
        added = [os.path.relpath(item.get_path(), subpath) for item in added]

        return modified, removed, added

    def pull(self, element, key, *, progress=None):
        project = element._get_project()

        artifact_map = self._artifact_maps[project]

        ref = self.get_artifact_fullname(element, key)

        try:
            # fetch the artifact from highest priority remote using the specified cache key
            remote = artifact_map.lookup_first(ref)
            remote_name = self._ensure_remote(self.repo, remote.pull_url)
            _ostree.fetch(self.repo, remote=remote_name, ref=ref, progress=progress)
        except OSTreeError as e:
            raise ArtifactError("Failed to pull artifact for element {}: {}"
                                .format(element.name, e)) from e

        self.__cache_size = None

    def link_key(self, element, oldkey, newkey):
        oldref = self.get_artifact_fullname(element, oldkey)
        newref = self.get_artifact_fullname(element, newkey)

        # resolve ref to checksum
        rev = _ostree.checksum(self.repo, oldref)

        # create additional ref for the same checksum
        _ostree.set_ref(self.repo, newref, rev)

    def push(self, element, keys):
        any_pushed = False

        project = element._get_project()

        push_remotes = [r for r in self._remotes[project] if r.spec.push]

        if not push_remotes:
            raise ArtifactError("Push is not enabled for any of the configured remote artifact caches.")

        refs = [self.get_artifact_fullname(element, key) for key in keys]

        remotes_for_each_ref = [self._remotes_containing_key(element, ref) for ref in refs]

        for remote in push_remotes:
            # Push if the remote is missing any of the refs
            if any([remote not in remotes_with_ref for remotes_with_ref in remotes_for_each_ref]):
                any_pushed |= self._push_to_remote(remote, element, refs)

        return any_pushed

    def get_cache_size(self):
        if self.__cache_size is None:
            self.__cache_size = utils._get_dir_size(self.repo.get_path().get_path())

        return self.__cache_size

    def initialize_remotes(self, *, on_failure=None):
        remote_specs = self.global_remote_specs

        for project in self.project_remote_specs:
            remote_specs += self.project_remote_specs[project]

        remote_specs = list(utils._deduplicate(remote_specs))

        remote_results = {}

        # Callback to initialize one remote in a 'multiprocessing' subprocess.
        #
        # We cannot do this in the main process because of the way the tasks
        # run by the main scheduler calls into libostree using
        # fork()-without-exec() subprocesses. OSTree fetch operations in
        # subprocesses hang if fetch operations were previously done in the
        # main process.
        #
        def child_action(url, q):
            try:
                push_url, pull_url = self._initialize_remote(url)
                remote = self._ensure_remote(self.repo, pull_url)
                remote_refs = _ostree.list_remote_refs(self.repo, remote=remote)
                q.put((None, push_url, pull_url, remote_refs))
            except Exception as e:               # pylint: disable=broad-except
                # Whatever happens, we need to return it to the calling process
                #
                q.put((str(e), None, None, None))

        # Kick off all the initialization jobs one by one.
        #
        # Note that we cannot use multiprocessing.Pool here because it's not
        # possible to pickle local functions such as child_action().
        #
        q = multiprocessing.Queue()
        for remote_spec in remote_specs:
            p = multiprocessing.Process(target=child_action, args=(remote_spec.url, q))

            try:

                # Keep SIGINT blocked in the child process
                with _signals.blocked([signal.SIGINT], ignore=False):
                    p.start()

                error, push_url, pull_url, remote_refs = q.get()
                p.join()
            except KeyboardInterrupt:
                utils._kill_process_tree(p.pid)
                raise

            if error and on_failure:
                on_failure(remote_spec.url, error)
            elif error:
                raise ArtifactError(error)
            else:
                if remote_spec.push and push_url:
                    self._has_push_remotes = True
                if pull_url:
                    self._has_fetch_remotes = True

                remote_results[remote_spec.url] = (push_url, pull_url, remote_refs)

        # Prepare push_urls, pull_urls, and remote_refs for each project
        for project in self.context.get_projects():
            remote_specs = self.global_remote_specs
            if project in self.project_remote_specs:
                remote_specs = list(utils._deduplicate(remote_specs + self.project_remote_specs[project]))

            remotes = []
            artifact_map = _OSTreeArtifactMap()

            for remote_spec in remote_specs:
                # Errors are already handled in the loop above,
                # skip unreachable remotes here.
                if remote_spec.url not in remote_results:
                    continue

                push_url, pull_url, remote_refs = remote_results[remote_spec.url]

                if remote_spec.push and not push_url:
                    raise ArtifactError("Push enabled but not supported by repo at: {}".format(remote_spec.url))

                remote = _OSTreeRemote(remote_spec, pull_url, push_url)
                remotes.append(remote)

                # Update our overall map of remote refs with any refs that are
                # present in the new remote and were not already found in
                # higher priority ones.
                for ref in remote_refs:
                    artifact_map.append(ref, remote)

            self._artifact_maps[project] = artifact_map
            self._remotes[project] = remotes

    ################################################
    #             Local Private Methods            #
    ################################################

    # _initialize_remote():
    #
    # Do protocol-specific initialization necessary to use a given OSTree
    # remote.
    #
    # The SSH protocol that we use only supports pushing so initializing these
    # involves contacting the remote to find out the corresponding pull URL.
    #
    # Args:
    #     url (str): URL of the remote
    #
    # Returns:
    #     (str, str): the pull URL and push URL for the remote
    #
    # Raises:
    #     ArtifactError: if there was an error
    def _initialize_remote(self, url):
        if url.startswith('ssh://'):
            try:
                push_url = url
                pull_url = initialize_push_connection(url)
            except PushException as e:
                raise ArtifactError(e) from e
        elif url.startswith('/'):
            push_url = pull_url = 'file://' + url
        elif url.startswith('file://'):
            push_url = pull_url = url
        elif url.startswith('http://') or url.startswith('https://'):
            push_url = None
            pull_url = url
        else:
            raise ArtifactError("Unsupported URL: {}".format(url))

        return push_url, pull_url

    # _ensure_remote():
    #
    # Ensure that our OSTree repo has a remote configured for the given URL.
    # Note that SSH access to remotes is not handled by libostree itself.
    #
    # Args:
    #     repo (OSTree.Repo): an OSTree repository
    #     pull_url (str): the URL where libostree can pull from the remote
    #
    # Returns:
    #     (str): the name of the remote, which can be passed to various other
    #            operations implemented by the _ostree module.
    #
    # Raises:
    #     OSTreeError: if there was a problem reported by libostree
    def _ensure_remote(self, repo, pull_url):
        remote_name = utils.url_directory_name(pull_url)
        _ostree.configure_remote(repo, remote_name, pull_url)
        return remote_name

    # _remotes_containing_key():
    #
    # Return every remote cache that contains the key. The result will be an
    # ordered list of remotes.
    #
    # Args:
    #     element (Element): The Element to check
    #     key (str): The key to use
    #
    # Returns (list): A list of _OSTreeRemote instances.
    #
    def _remotes_containing_key(self, element, key):
        if not self._has_fetch_remotes:
            return []

        artifact_map = self._artifact_maps[element._get_project()]
        ref = self.get_artifact_fullname(element, key)
        return artifact_map.lookup(ref)

    def _push_to_remote(self, remote, element, refs):
        with utils._tempdir(dir=self.context.artifactdir, prefix='push-repo-') as temp_repo_dir:

            with element.timed_activity("Preparing compressed archive"):
                # First create a temporary archive-z2 repository, we can
                # only use ostree-push with archive-z2 local repo.
                temp_repo = _ostree.ensure(temp_repo_dir, True)

                # Now push the ref we want to push into our temporary archive-z2 repo
                for ref in refs:
                    _ostree.fetch(temp_repo, remote=self.repo.get_path().get_uri(), ref=ref)

            with element.timed_activity("Sending artifact"), \
                element._output_file() as output_file:
                try:
                    pushed = push_artifact(temp_repo.get_path().get_path(),
                                           remote.push_url,
                                           refs, output_file)
                except PushException as e:
                    raise ArtifactError("Failed to push artifact {}: {}".format(refs, e)) from e

            return pushed


# Represents a single remote OSTree cache.
#
class _OSTreeRemote():
    def __init__(self, spec, pull_url, push_url):
        self.spec = spec
        self.pull_url = pull_url
        self.push_url = push_url


# Maps artifacts to the remotes that contain them.
#
class _OSTreeArtifactMap():
    def __init__(self):
        self._ref_to_remotes = {}

    def append(self, ref, remote):
        if ref in self._ref_to_remotes:
            self._ref_to_remotes[ref].append(remote)
        else:
            self._ref_to_remotes[ref] = [remote]

    def lookup(self, ref):
        return self._ref_to_remotes.get(ref, [])

    def lookup_first(self, ref):
        return self._ref_to_remotes.get(ref, [])[0]

    def contains(self, ref):
        return ref in self._ref_to_remotes
