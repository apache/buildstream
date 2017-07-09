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

import os
import tempfile

from . import _ostree, utils
from .exceptions import _BstError
from ._ostree import OSTreeError


# For users of this file, they must expect (except) it.
class ArtifactError(_BstError):
    pass


def buildref(element):
    project = element.get_project()
    key = element._get_cache_key()

    # Normalize ostree ref unsupported chars
    element_name = element.normal_name.replace('+', 'X')

    # assume project and element names are not allowed to contain slashes
    return '{0}/{1}/{2}'.format(project.name, element_name, key)


# An ArtifactCache manages artifacts in an OSTree repository
#
# Args:
#     context (Context): The BuildStream context
#
class ArtifactCache():
    def __init__(self, context):

        self.context = context

        os.makedirs(context.artifactdir, exist_ok=True)
        ostreedir = os.path.join(context.artifactdir, 'ostree')
        self.extractdir = os.path.join(context.artifactdir, 'extract')
        self.repo = _ostree.ensure(ostreedir, False)

        if self.context.artifact_pull:
            self.remote = utils.url_directory_name(context.artifact_pull)
            _ostree.configure_remote(self.repo, self.remote, self.context.artifact_pull)
        else:
            self.remote = None

    # contains():
    #
    # Check whether the artifact for the specified Element is already available
    # in the local artifact cache.
    #
    # Args:
    #     element (Element): The Element to check
    #
    # Returns: True if the artifact is in the cache, False otherwise
    #
    def contains(self, element):
        if not element._get_cache_key():
            return False

        ref = buildref(element)
        return _ostree.exists(self.repo, ref)

    # remove():
    #
    # Removes the artifact for the specified Element from the local artifact
    # cache.
    #
    # Args:
    #     element (Element): The Element to remove
    #
    def remove(self, element):
        if not element._get_cache_key():
            return

        ref = buildref(element)
        _ostree.remove(self.repo, ref)

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
        ref = buildref(element)

        dest = os.path.join(self.extractdir, ref)
        if os.path.isdir(dest):
            # artifact has already been extracted
            return dest

        # resolve ref to checksum
        rev = _ostree.checksum(self.repo, ref)
        if not rev:
            raise ArtifactError("Artifact missing for {}".format(ref))

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
        ref = buildref(element)

        _ostree.commit(self.repo, content, ref)

    # can_fetch():
    #
    # Check whether remote repository is available for fetching.
    #
    # Returns: True if remote repository is available, False otherwise
    #
    def can_fetch(self):
        return self.remote is not None

    # pull():
    #
    # Pull artifact from remote repository.
    #
    # Args:
    #     element (Element): The Element whose artifact is to be fetched
    #     progress (callable): The progress callback, if any
    #
    def pull(self, element, progress=None):

        if self.context.artifact_pull.startswith("/"):
            remote = "file://" + self.context.artifact_pull
        elif self.remote is not None:
            remote = self.remote
        else:
            raise ArtifactError("Attempt to pull artifact without any pull URL")

        ref = buildref(element)
        try:
            _ostree.fetch(self.repo, remote=remote,
                          ref=ref, progress=progress)
        except OSTreeError as e:
            raise ArtifactError("Failed to pull artifact for element {}: {}"
                                .format(element.name, e)) from e

    # can_push():
    #
    # Check whether remote repository is available for pushing.
    #
    # Returns: True if remote repository is available, False otherwise
    #
    def can_push(self):
        return self.context.artifact_push is not None

    # push():
    #
    # Push committed artifact to remote repository.
    #
    # Args:
    #     element (Element): The Element whose artifact is to be pushed
    #
    def push(self, element):

        if self.context.artifact_push is None:
            raise ArtifactError("Attempt to push artifact without any push URL")

        ref = buildref(element)
        workdir = os.path.join(self.context.artifactdir, 'work')
        os.makedirs(workdir, exist_ok=True)

        with element._output_file() as output_file:
            _ostree.push(self.repo, workdir,
                         remote=self.context.artifact_push, ref=ref,
                         output_file=output_file)
