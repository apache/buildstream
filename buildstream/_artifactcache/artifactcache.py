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
#        Tristan Maat <tristan.maat@codethink.co.uk>

import os
from collections import Mapping, namedtuple

from .._exceptions import ImplError, LoadError, LoadErrorReason
from .. import utils
from .. import _yaml


# An ArtifactCacheSpec holds the user configuration for a single remote
# artifact cache.
#
# Args:
#     url (str): Location of the remote artifact cache
#     push (bool): Whether we should attempt to push artifacts to this cache,
#                  in addition to pulling from it.
#
class ArtifactCacheSpec(namedtuple('ArtifactCacheSpec', 'url push')):
    @staticmethod
    def new_from_config_node(spec_node):
        _yaml.node_validate(spec_node, ['url', 'push'])
        url = _yaml.node_get(spec_node, str, 'url')
        push = _yaml.node_get(spec_node, bool, 'push', default_value=False)
        if len(url) == 0:
            provenance = _yaml.node_get_provenance(spec_node)
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: empty artifact cache URL".format(provenance))
        return ArtifactCacheSpec(url, push)


# artifact_cache_specs_from_config_node()
#
# Parses the configuration of remote artifact caches from a config block.
#
# Args:
#   config_node (dict): The config block, which may contain the 'artifacts' key
#
# Returns:
#   A list of ArtifactCacheSpec instances.
#
# Raises:
#   LoadError, if the config block contains invalid keys.
#
def artifact_cache_specs_from_config_node(config_node):
    cache_specs = []

    artifacts = config_node.get('artifacts', [])
    if isinstance(artifacts, Mapping):
        cache_specs.append(ArtifactCacheSpec.new_from_config_node(artifacts))
    elif isinstance(artifacts, list):
        for spec_node in artifacts:
            cache_specs.append(ArtifactCacheSpec.new_from_config_node(spec_node))
    else:
        provenance = _yaml.node_get_provenance(config_node, key='artifacts')
        raise _yaml.LoadError(_yaml.LoadErrorReason.INVALID_DATA,
                              "%s: 'artifacts' must be a single 'url:' mapping, or a list of mappings" %
                              (str(provenance)))
    return cache_specs


# configured_remote_artifact_cache_specs():
#
# Return the list of configured artifact remotes for a given project, in priority
# order. This takes into account the user and project configuration.
#
# Args:
#     context (Context): The BuildStream context
#     project (Project): The BuildStream project
#
# Returns:
#   A list of ArtifactCacheSpec instances describing the remote artifact caches.
#
def configured_remote_artifact_cache_specs(context, project):
    project_overrides = context._get_overrides(project.name)
    project_extra_specs = artifact_cache_specs_from_config_node(project_overrides)

    return list(utils._deduplicate(
        project_extra_specs + project.artifact_cache_specs + context.artifact_cache_specs))


# An ArtifactCache manages artifacts.
#
# Args:
#     context (Context): The BuildStream context
#
class ArtifactCache():
    def __init__(self, context):

        self.context = context

        os.makedirs(context.artifactdir, exist_ok=True)
        self.extractdir = os.path.join(context.artifactdir, 'extract')

        self._local = False
        self.global_remote_specs = []
        self.project_remote_specs = {}

    # set_remotes():
    #
    # Set the list of remote caches. If project is None, the global list of
    # remote caches will be set, which is used by all projects. If a project is
    # specified, the per-project list of remote caches will be set.
    #
    # Args:
    #     remote_specs (list): List of ArtifactCacheSpec instances, in priority order.
    #     project (Project): The Project instance for project-specific remotes
    def set_remotes(self, remote_specs, *, project=None):
        if project is None:
            # global remotes
            self.global_remote_specs = remote_specs
        else:
            self.project_remote_specs[project] = remote_specs

    # initialize_remotes():
    #
    # This will contact each remote cache.
    #
    # Args:
    #     on_failure (callable): Called if we fail to contact one of the caches.
    #
    def initialize_remotes(self, *, on_failure=None):
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

    # has_fetch_remotes():
    #
    # Check whether any remote repositories are available for fetching.
    #
    # Returns: True if any remote repositories are configured, False otherwise
    #
    def has_fetch_remotes(self):
        return False

    # has_push_remotes():
    #
    # Check whether any remote repositories are available for pushing.
    #
    # Args:
    #     element (Element): The Element to check
    #
    # Returns: True if any remote repository is configured, False otherwise
    #
    def has_push_remotes(self, *, element=None):
        return False

    # remote_contains_key():
    #
    # Check whether the artifact for the specified Element is already available
    # in any remote artifact cache.
    #
    # Args:
    #     element (Element): The Element to check
    #     strength (_KeyStrength): Either STRONG or WEAK key strength, or None
    #
    # Returns: True if the artifact is in the cache, False otherwise
    #
    def remote_contains(self, element, strength=None):
        return False
