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
import string
import tempfile

from .. import _ostree, _signals, utils
from .._exceptions import ArtifactError
from ..element import _KeyStrength
from .._ostree import OSTreeError

from . import ArtifactCache
from .pushreceive import initialize_push_connection
from .pushreceive import push as push_artifact
from .pushreceive import PushException


def buildref(element, key):
    project = element._get_project()

    # Normalize ostree ref unsupported chars
    valid_chars = string.digits + string.ascii_letters + '-._'
    element_name = ''.join([
        x if x in valid_chars else '_'
        for x in element.normal_name
    ])

    if key is None:
        raise ArtifactError('Cache key missing')

    # assume project and element names are not allowed to contain slashes
    return '{0}/{1}/{2}'.format(project.name, element_name, key)


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

    # contains():
    #
    # Check whether the artifact for the specified Element is already available
    # in the local artifact cache.
    #
    # Args:
    #     element (Element): The Element to check
    #     key (str): The cache key to use
    #
    # Returns: True if the artifact is in the cache, False otherwise
    #
    def contains(self, element, key):
        ref = buildref(element, key)
        return _ostree.exists(self.repo, ref)

    # remotes_containing_key():
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
    def remotes_containing_key(self, element, key):
        if not self._has_fetch_remotes:
            return []

        artifact_map = self._artifact_maps[element._get_project()]
        ref = buildref(element, key)
        return artifact_map.lookup(ref)

    # remote_contains():
    #
    # Check whether the artifact for the specified Element is already available
    # in the remote artifact cache.
    #
    # Args:
    #     element (Element): The Element to check
    #     key (str): The cache key to use
    #
    # Returns: True if the artifact is in a cache, False otherwise
    #
    def remote_contains(self, element, key):
        remotes = self.remotes_containing_key(element, key)
        return len(remotes) > 0

    # push_needed():
    #
    # Check whether an artifact for the specified Element needs to be pushed to
    # any of the configured push remotes. The policy is to push every artifact
    # we build to every configured push remote, so this should only return False
    # if all of the configured push remotes already contain the given artifact.
    #
    # This function checks for presence of the artifact only using its strong
    # key. The presence of the weak key in a cache does not necessarily indicate
    # that this particular artifact is present, only that there is a
    # partially-compatible version available.
    #
    # Args:
    #     element (Element): The Element to check
    #
    # Returns: False if all the push remotes have the artifact, True otherwise
    #
    def push_needed(self, element):
        key = element._get_cache_key(strength=_KeyStrength.STRONG)

        if not key:
            return False

        remotes_with_artifact = self.remotes_containing_key(element, key)

        push_remotes_with_artifact = set(r for r in remotes_with_artifact if r.spec.push)
        push_remotes_for_project = set(self._remotes[element._get_project()])
        return not (push_remotes_for_project.issubset(push_remotes_with_artifact))

    # extract():
    #
    # Extract cached artifact for the specified Element if it hasn't
    # already been extracted.
    #
    # Assumes artifact has previously been fetched or committed.
    #
    # Args:
    #     element (Element): The Element to extract
    #     key (str): The cache key to use
    #
    # Raises:
    #     ArtifactError: In cases there was an OSError, or if the artifact
    #                    did not exist.
    #
    # Returns: path to extracted artifact
    #
    def extract(self, element, key):
        ref = buildref(element, key)

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

    # commit():
    #
    # Commit built artifact to cache.
    #
    # Args:
    #     element (Element): The Element commit an artifact for
    #     content (str): The element's content directory
    #
    def commit(self, element, content):
        # tag with strong cache key based on dependency versions used for the build
        ref = buildref(element, element._get_cache_key())

        # also store under weak cache key
        weak_ref = buildref(element, element._get_cache_key(strength=_KeyStrength.WEAK))

        try:
            _ostree.commit(self.repo, content, [ref, weak_ref])
        except OSTreeError as e:
            raise ArtifactError("Failed to commit artifact: {}".format(e)) from e

    # pull():
    #
    # Pull artifact from one of the configured remote repositories.
    #
    # Args:
    #     element (Element): The Element whose artifact is to be fetched
    #     progress (callable): The progress callback, if any
    #
    def pull(self, element, progress=None):
        project = element._get_project()

        artifact_map = self._artifact_maps[project]

        ref = buildref(element, element._get_strict_cache_key())
        weak_ref = buildref(element, element._get_cache_key(strength=_KeyStrength.WEAK))

        try:
            if artifact_map.contains(ref):
                # fetch the artifact from highest priority remote using the strong cache key
                remote = artifact_map.lookup_first(ref)
                remote_name = self._ensure_remote(self.repo, remote.pull_url)
                _ostree.fetch(self.repo, remote=remote_name, ref=ref, progress=progress)

                # resolve ref to checksum
                rev = _ostree.checksum(self.repo, ref)

                # update weak ref by pointing it to this newly fetched artifact
                _ostree.set_ref(self.repo, weak_ref, rev)
            elif artifact_map.contains(weak_ref):
                # fetch the artifact from the highest priority cache using the weak cache key
                remote = artifact_map.lookup_first(weak_ref)
                remote_name = self._ensure_remote(self.repo, remote.pull_url)
                _ostree.fetch(self.repo, remote=remote_name, ref=weak_ref, progress=progress)

                # resolve weak_ref to checksum
                rev = _ostree.checksum(self.repo, weak_ref)

                # extract strong cache key from this newly fetched artifact
                element._update_state()
                ref = buildref(element, element._get_cache_key())

                # create tag for strong cache key
                _ostree.set_ref(self.repo, ref, rev)
            else:
                raise ArtifactError("Attempt to pull unavailable artifact for element {}"
                                    .format(element.name))
        except OSTreeError as e:
            raise ArtifactError("Failed to pull artifact for element {}: {}"
                                .format(element.name, e)) from e

    # push():
    #
    # Push committed artifact to remote repository.
    #
    # Args:
    #     element (Element): The Element whose artifact is to be pushed
    #
    # Returns:
    #   (bool): True if any remote was updated, False if no pushes were required
    #
    # Raises:
    #   (ArtifactError): if there was an error
    def push(self, element):
        any_pushed = False

        project = element._get_project()

        push_remotes = [r for r in self._remotes[project] if r.spec.push]

        if len(push_remotes) == 0:
            raise ArtifactError("Push is not enabled for any of the configured remote artifact caches.")

        ref = buildref(element, element._get_cache_key())
        weak_ref = buildref(element, element._get_cache_key(strength=_KeyStrength.WEAK))

        remotes_with_ref = self.remotes_containing_key(element, ref)
        remotes_with_weak_ref = self.remotes_containing_key(element, weak_ref)

        for remote in push_remotes:
            if remote not in remotes_with_ref or remote not in remotes_with_weak_ref:
                any_pushed |= self._push_to_remote(remote, element, ref, weak_ref)

        return any_pushed

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
            except Exception as e:
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
        for project in self.context._get_projects():
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

    def _push_to_remote(self, remote, element, ref, weak_ref):
        with utils._tempdir(dir=self.context.artifactdir, prefix='push-repo-') as temp_repo_dir:

            with element.timed_activity("Preparing compressed archive"):
                # First create a temporary archive-z2 repository, we can
                # only use ostree-push with archive-z2 local repo.
                temp_repo = _ostree.ensure(temp_repo_dir, True)

                # Now push the ref we want to push into our temporary archive-z2 repo
                _ostree.fetch(temp_repo, remote=self.repo.get_path().get_uri(), ref=ref)
                _ostree.fetch(temp_repo, remote=self.repo.get_path().get_uri(), ref=weak_ref)

            with element.timed_activity("Sending artifact"), \
                element._output_file() as output_file:
                try:
                    pushed = push_artifact(temp_repo.get_path().get_path(),
                                           remote.push_url,
                                           [ref, weak_ref], output_file)
                except PushException as e:
                    raise ArtifactError("Failed to push artifact {}: {}".format(ref, e)) from e

            return pushed
