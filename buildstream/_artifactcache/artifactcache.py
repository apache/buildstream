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

from .._exceptions import ImplError
from .. import utils
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

        self._local = False

        project_overrides = context._get_overrides(project.name)
        artifact_overrides = _yaml.node_get(project_overrides, Mapping, 'artifacts', default_value={})
        override_url = _yaml.node_get(artifact_overrides, str, 'url', default_value='') or None

        _yaml.node_validate(artifact_overrides, ['url'])

        if override_url:
            self.url = override_url
        elif project.artifact_url:
            self.url = project.artifact_url
        else:
            self.url = context.artifact_url

        if self.url:
            if self.url.startswith('/') or self.url.startswith('file://'):
                self._local = True

            self.remote = utils.url_directory_name(self.url)
        else:
            self.remote = None

        self._offline = False

    # initialize_remote():
    #
    # Initialize any remote artifact cache, if needed. This may require network
    # access and could block for several seconds.
    #
    def initialize_remote(self):
        pass

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
    #     ArtifactError: In cases there was an OSError, or if the artifact
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
        return (not self._offline or self._local) and \
            self.remote is not None

    # can_push():
    #
    # Check whether remote repository is available for pushing.
    #
    # Returns: True if remote repository is available, False otherwise
    #
    def can_push(self):
        return (not self._offline or self._local) and \
            self.url is not None

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

    def fetch_remote_refs(self):
        pass
