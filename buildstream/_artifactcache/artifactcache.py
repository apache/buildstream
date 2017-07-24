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
#        Tristan Maat <tristan.maat@codethink.co.uk>

import os

from .. import utils, ImplError


class ArtifactCache():
    def __init__(self, context):

        self.context = context

        os.makedirs(context.artifactdir, exist_ok=True)
        self.extractdir = os.path.join(context.artifactdir, 'extract')

        self._offline = False
        self._pull_local = False
        self._push_local = False

        if self.context.artifact_push:
            if self.context.artifact_push.startswith("/") or \
               self.context.artifact_push.startswith("file://"):
                self._push_local = True

        if self.context.artifact_pull:
            if self.context.artifact_pull.startswith("/") or \
               self.context.artifact_pull.startswith("file://"):
                self._pull_local = True

            self.remote = utils.url_directory_name(context.artifact_pull)
        else:
            self.remote = None

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
        raise ImplError("Cache '{kind}' does not implement contains()"
                        .format(kind=type(self).__name__))

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
        raise ImplError("Cache '{kind}' does not implement extract()"
                        .format(kind=type(self).__name__))

    # commit():
    #
    # Commit built artifact to cache.
    #
    # Args:
    #     element (Element): The Element commit an artifact for
    #     content (str): The element's content directory
    #
    def commit(self, element, content):
        raise ImplError("Cache '{kind}' does not implement commit()"
                        .format(kind=type(self).__name__))

    # set_offline()
    #
    # Do not attempt to pull or push artifacts.
    #
    def set_offline(self):
        self._offline = True

    # can_fetch():
    #
    # Check whether remote repository is available for fetching.
    #
    # Returns: True if remote repository is available, False otherwise
    #
    def can_fetch(self):
        return (not self._offline or self._pull_local) and \
            self.remote is not None

    # can_push():
    #
    # Check whether remote repository is available for pushing.
    #
    # Returns: True if remote repository is available, False otherwise
    #
    def can_push(self):
        return (not self._offline or self._push_local) and \
            self.context.artifact_push is not None

    # remote_contains_key():
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
        return False
