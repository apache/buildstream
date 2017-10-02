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
from collections import Mapping

from .. import utils, ImplError
from .. import _yaml


# An ArtifactCache manages artifacts
#
# Args:
#     context (Context): The BuildStream context
#     project (Project): The BuildStream project
#
class ArtifactCache():
    def __init__(self, context, project):

        self.context = context

        os.makedirs(context.artifactdir, exist_ok=True)
        self.extractdir = os.path.join(context.artifactdir, 'extract')

        self._pull_local = False
        self._push_local = False

        project_overrides = context._get_overrides(project.name)
        artifact_overrides = _yaml.node_get(project_overrides, Mapping, 'artifacts', default_value={})
        override_pull = _yaml.node_get(artifact_overrides, str, 'pull-url', default_value='') or None
        override_push = _yaml.node_get(artifact_overrides, str, 'push-url', default_value='') or None
        override_push_port = _yaml.node_get(artifact_overrides, int, 'push-port', default_value=22)

        _yaml.node_validate(artifact_overrides, ['pull-url', 'push-url', 'push-port'])

        if override_pull or override_push:
            self.artifact_pull = override_pull
            self.artifact_push = override_push
            self.artifact_push_port = override_push_port

        elif any((project.artifact_pull, project.artifact_push)):
            self.artifact_pull = project.artifact_pull
            self.artifact_push = project.artifact_push
            self.artifact_push_port = project.artifact_push_port

        else:
            self.artifact_pull = context.artifact_pull
            self.artifact_push = context.artifact_push
            self.artifact_push_port = context.artifact_push_port

        if self.artifact_push:
            if self.artifact_push.startswith("/") or \
               self.artifact_push.startswith("file://"):
                self._push_local = True

        if self.artifact_pull:
            if self.artifact_pull.startswith("/") or \
               self.artifact_pull.startswith("file://"):
                self._pull_local = True

            self.remote = utils.url_directory_name(self.artifact_pull)
        else:
            self.remote = None

        self._offline = False

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
            self.artifact_push is not None

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
