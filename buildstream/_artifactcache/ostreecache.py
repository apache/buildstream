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
from .._exceptions import _ArtifactError
from ..element import _KeyStrength
from .._ostree import OSTreeError

from . import ArtifactCache
from .pushreceive import check_push_connection
from .pushreceive import push as push_artifact
from .pushreceive import PushException


def buildref(element, key):
    project = element.get_project()

    # Normalize ostree ref unsupported chars
    valid_chars = string.digits + string.ascii_letters + '-._'
    element_name = ''.join([
        x if x in valid_chars else '_'
        for x in element.normal_name
    ])

    # assume project and element names are not allowed to contain slashes
    return '{0}/{1}/{2}'.format(project.name, element_name, key)


# An ArtifactCache manages artifacts in an OSTree repository
#
# Args:
#     context (Context): The BuildStream context
#     project (Project): The BuildStream project
#     enable_push (bool): Whether pushing is allowed
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

        if self.artifact_pull:
            _ostree.configure_remote(self.repo, self.remote, self.artifact_pull)

        self._remote_refs = None

    def can_push(self):
        if self.enable_push:
            return super().can_push()
        return False

    def preflight(self):
        if self.can_push() and not self.artifact_push.startswith("/"):
            try:
                check_push_connection(self.artifact_push,
                                      self.artifact_push_port)
            except PushException as e:
                raise _ArtifactError("BuildStream will be unable to push artifacts "
                                     "to the shared cache: {}".format(e))

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
        if not self._remote_refs:
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
    #     _ArtifactError: In cases there was an OSError, or if the artifact
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
            raise _ArtifactError("Artifact missing for {}".format(ref))

        dest = os.path.join(self.extractdir, element.get_project().name, element.normal_name, rev)
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
                    raise _ArtifactError("Failed to extract artifact for ref '{}': {}"
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
            raise _ArtifactError("Failed to commit artifact: {}".format(e)) from e

    # pull():
    #
    # Pull artifact from remote repository.
    #
    # Args:
    #     element (Element): The Element whose artifact is to be fetched
    #     progress (callable): The progress callback, if any
    #
    def pull(self, element, progress=None):

        if self._offline and not self._pull_local:
            raise _ArtifactError("Attempt to pull artifact while offline")

        if self.artifact_pull.startswith("/"):
            remote = "file://" + self.artifact_pull
        elif self.remote is not None:
            remote = self.remote
        else:
            raise _ArtifactError("Attempt to pull artifact without any pull URL")

        weak_ref = buildref(element, element._get_cache_key(strength=_KeyStrength.WEAK))

        try:
            if self.remote_contains(element, strength=_KeyStrength.STRONG):
                # fetch the artifact using the strong cache key
                ref = buildref(element, element._get_cache_key())
                _ostree.fetch(self.repo, remote=remote,
                              ref=ref, progress=progress)

                # resolve ref to checksum
                rev = _ostree.checksum(self.repo, ref)

                # update weak ref by pointing it to this newly fetched artifact
                _ostree.set_ref(self.repo, weak_ref, rev)
            elif self.remote_contains(element):
                # fetch the artifact using the weak cache key
                _ostree.fetch(self.repo, remote=remote,
                              ref=weak_ref, progress=progress)

                # resolve weak_ref to checksum
                rev = _ostree.checksum(self.repo, weak_ref)

                # extract strong cache key from this newly fetched artifact
                element._cached(recalculate=True)
                ref = buildref(element, element._get_cache_key_from_artifact())

                # create tag for strong cache key
                _ostree.set_ref(self.repo, ref, rev)
            else:
                raise _ArtifactError("Attempt to pull unavailable artifact for element {}"
                                     .format(element.name))
        except OSTreeError as e:
            raise _ArtifactError("Failed to pull artifact for element {}: {}"
                                 .format(element.name, e)) from e

    # fetch_remote_refs():
    #
    # Fetch list of artifacts from remote repository.
    #
    def fetch_remote_refs(self):
        if self.artifact_pull.startswith("/"):
            remote = "file://" + self.artifact_pull
        elif self.remote is not None:
            remote = self.remote
        else:
            raise _ArtifactError("Attempt to fetch remote refs without any pull URL")

        def child_action(repo, remote, q):
            try:
                q.put((True, _ostree.list_remote_refs(self.repo, remote=remote)))
            except OSTreeError as e:
                q.put((False, e))

        q = multiprocessing.Queue()
        p = multiprocessing.Process(target=child_action, args=(self.repo, remote, q))
        p.start()
        ret, res = q.get()
        p.join()

        if ret:
            self._remote_refs = res
        else:
            raise _ArtifactError("Failed to fetch remote refs") from res

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
    #   _ArtifactError if there was an error
    def push(self, element):

        if self._offline and not self._push_local:
            raise _ArtifactError("Attempt to push artifact while offline")

        if self.artifact_push is None:
            raise _ArtifactError("Attempt to push artifact without any push URL")

        ref = buildref(element, element._get_cache_key_from_artifact())
        weak_ref = buildref(element, element._get_cache_key(strength=_KeyStrength.WEAK))
        if self.artifact_push.startswith("/"):
            # local repository
            push_repo = _ostree.ensure(self.artifact_push, True)
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
                                               self.artifact_push,
                                               self.artifact_push_port,
                                               [ref, weak_ref], output_file)
                    except PushException as e:
                        raise _ArtifactError("Failed to push artifact {}: {}".format(ref, e)) from e

                return pushed

    # set_offline():
    #
    # Do not attempt to pull or push artifacts.
    #
    def set_offline(self):
        self._offline = True
