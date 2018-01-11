#!/usr/bin/env python3
#
#  Copyright (C) 2017 Codethink Limited
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
import string
import tempfile

from .. import _ostree, utils
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

    # assume project and element names are not allowed to contain slashes
    return '{0}/{1}/{2}'.format(project.name, element_name, key)


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

    def __init__(self, context, project, enable_push):
        super().__init__(context, project)

        self.enable_push = enable_push

        ostreedir = os.path.join(context.artifactdir, 'ostree')
        self.repo = _ostree.ensure(ostreedir, False)

        self.push_urls = []
        self.pull_urls = []
        self._remote_refs = {}

    def set_remotes(self, remote_specs, on_failure=None):
        self.remote_specs = remote_specs

        self._initialize_remotes(on_failure)

    def has_fetch_remotes(self):
        return (len(self.pull_urls) > 0)

    def has_push_remotes(self):
        return (len(self.push_urls) > 0)

    # contains():
    #
    # Check whether the artifact for the specified Element is already available
    # in the local artifact cache.
    #
    # Args:
    #     element (Element): The Element to check
    #     strength (_KeyStrength): Either STRONG or WEAK key strength, or None
    #
    # Returns: True if the artifact is in the cache, False otherwise
    #
    def contains(self, element, strength=None):
        if strength is None:
            strength = _KeyStrength.STRONG if element._get_strict() else _KeyStrength.WEAK

        key = element._get_cache_key(strength)
        if not key:
            return False

        ref = buildref(element, key)
        return _ostree.exists(self.repo, ref)

    # remote_contains_key():
    #
    # Check whether the artifact for the specified Element is already available
    # in the remote artifact cache.
    #
    # Args:
    #     element (Element): The Element to check
    #     key (str): The key to use
    #
    # Returns: True if the artifact is in the cache, False otherwise
    #
    def remote_contains_key(self, element, key):
        if len(self._remote_refs) == 0:
            return False

        ref = buildref(element, key)
        return ref in self._remote_refs

    # remote_contains():
    #
    # Check whether the artifact for the specified Element is already available
    # in the remote artifact cache.
    #
    # Args:
    #     element (Element): The Element to check
    #     strength (_KeyStrength): Either STRONG or WEAK key strength, or None
    #
    # Returns: True if the artifact is in the cache, False otherwise
    #
    def remote_contains(self, element, strength=None):
        if strength is None:
            strength = _KeyStrength.STRONG if element._get_strict() else _KeyStrength.WEAK

        key = element._get_cache_key(strength)
        if not key:
            return False

        return self.remote_contains_key(element, key)

    # extract():
    #
    # Extract cached artifact for the specified Element if it hasn't
    # already been extracted.
    #
    # Assumes artifact has previously been fetched or committed.
    #
    # Args:
    #     element (Element): The Element to extract
    #
    # Raises:
    #     ArtifactError: In cases there was an OSError, or if the artifact
    #                    did not exist.
    #
    # Returns: path to extracted artifact
    #
    def extract(self, element):
        ref = buildref(element, element._get_cache_key())

        # resolve ref to checksum
        rev = _ostree.checksum(self.repo, ref)

        # resolve weak cache key, if artifact is missing for strong cache key
        # and the context allows use of weak cache keys
        if not rev and not element._get_strict():
            ref = buildref(element, element._get_cache_key(strength=_KeyStrength.WEAK))
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
        ref = buildref(element, element._get_cache_key_for_build())

        # also store under weak cache key
        weak_ref = buildref(element, element._get_cache_key(strength=_KeyStrength.WEAK))

        try:
            _ostree.commit(self.repo, content, ref, weak_ref)
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

        ref = buildref(element, element._get_cache_key())
        weak_ref = buildref(element, element._get_cache_key(strength=_KeyStrength.WEAK))

        try:
            if ref in self._remote_refs:
                # fetch the artifact using the strong cache key
                _ostree.fetch(self.repo, remote=self._remote_refs[ref],
                              ref=ref, progress=progress)

                # resolve ref to checksum
                rev = _ostree.checksum(self.repo, ref)

                # update weak ref by pointing it to this newly fetched artifact
                _ostree.set_ref(self.repo, weak_ref, rev)
            elif weak_ref in self._remote_refs:
                # fetch the artifact using the weak cache key
                _ostree.fetch(self.repo, remote=self._remote_refs[weak_ref],
                              ref=weak_ref, progress=progress)

                # resolve weak_ref to checksum
                rev = _ostree.checksum(self.repo, weak_ref)

                # extract strong cache key from this newly fetched artifact
                element._cached(recalculate=True)
                ref = buildref(element, element._get_cache_key_from_artifact())

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
    #   (bool): True if the remote was updated, False if it already existed
    #           and no updated was required
    #
    # Raises:
    #   (ArtifactError): if there was an error
    def push(self, element):
        any_pushed = False

        if len(self.push_urls) == 0:
            raise ArtifactError("Push is not enabled for any of the configured remote artifact caches.")

        ref = buildref(element, element._get_cache_key_from_artifact())
        weak_ref = buildref(element, element._get_cache_key(strength=_KeyStrength.WEAK))
        for push_url in self.push_urls:
            any_pushed |= self._push_to_remote(push_url, element, ref, weak_ref)

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
                raise ArtifactError("BuildStream did not connect successfully "
                                    "to the shared cache {}: {}".format(url, e))
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

    def _initialize_remotes(self, on_failure=None):
        self.push_url = None
        self.pull_urls = []
        self._remote_refs = {}

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
                # Exceptions aren't automatically propagated by
                # multiprocessing, so we catch everything here. Note that
                # GLib.Error subclasses can't be returned (as they don't
                # 'pickle') and so they'll be ignored.
                q.put((e, None, None, None))

        # Kick off all the initialization jobs one by one.
        #
        # Note that we cannot use multiprocessing.Pool here because it's not
        # possible to pickle local functions such as child_action().
        #
        q = multiprocessing.Queue()
        for remote in self.remote_specs:
            p = multiprocessing.Process(target=child_action, args=(remote.url, q))
            p.start()
            exception, push_url, pull_url, remote_refs = q.get()
            p.join()

            if exception and on_failure:
                on_failure(remote.url, exception)
            elif exception:
                raise ArtifactError() from exception
            else:
                if remote.push:
                    if push_url:
                        self.push_urls.append(push_url)
                    else:
                        raise ArtifactError("Push enabled but not supported by repo at: {}".format(remote.url))

                # The specs are deduplicated when reading the config, but since
                # each push URL can supply an arbitrary pull URL we must dedup
                # those again here.
                if pull_url and pull_url not in self.pull_urls:
                    self.pull_urls.append(pull_url)

                # Update our overall map of remote refs with any refs that are
                # present in the new remote and were not already found in
                # higher priority ones.
                remote = self._ensure_remote(self.repo, pull_url)
                for ref in remote_refs:
                    if ref not in self._remote_refs:
                        self._remote_refs[ref] = remote

    def _push_to_remote(self, push_url, element, ref, weak_ref):
        if push_url.startswith("file://"):
            # local repository
            push_repo = _ostree.ensure(push_url[7:], True)
            _ostree.fetch(push_repo, remote=self.repo.get_path().get_uri(), ref=ref)
            _ostree.fetch(push_repo, remote=self.repo.get_path().get_uri(), ref=weak_ref)

            # Local remotes are not really a thing, just return True here
            return True
        else:
            # Push over ssh
            #
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
                                               push_url,
                                               [ref, weak_ref], output_file)
                    except PushException as e:
                        raise ArtifactError("Failed to push artifact {}: {}".format(ref, e)) from e

                return pushed
