#!/usr/bin/env python3
#
#  Copyright (C) 2016 Codethink Limited
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

"""Loaded Project Configuration

The :class:`.Project` object holds all of the project settings from
the project configuration file including the project directory it
was loaded from.
"""

import os
import multiprocessing  # for cpu_count()
from collections import Mapping
from . import utils
from . import _site
from . import _yaml
from . import _loader  # For resolve_arch()
from ._profile import Topics, profile_start, profile_end
from . import LoadError, LoadErrorReason

# The separator we use for user specified aliases
_ALIAS_SEPARATOR = ':'


class Project():
    """Project Configuration

    Args:
       directory (str): The project directory
       host_arch (str): Symbolic host machine architecture name
       target_arch (str): Symbolic target machine architecture name

    Raises:
       :class:`.LoadError`
    """
    def __init__(self, directory, host_arch, target_arch=None):

        host_arch = host_arch
        target_arch = target_arch or host_arch

        self.name = None
        """str: The project name"""

        self.directory = os.path.abspath(directory)
        """str: The project directory"""

        self.element_path = None
        """str: Absolute path to where elements are loaded from within the project"""

        self._variables = {}    # The default variables overridden with project wide overrides
        self._environment = {}  # The base sandbox environment
        self._elements = {}     # Element specific configurations
        self._aliases = {}      # Aliases dictionary
        self.__workspaces = {}   # Workspaces
        self._plugin_source_paths = []   # Paths to custom sources
        self._plugin_element_paths = []  # Paths to custom plugins
        self._cache_key = None

        profile_start(Topics.LOAD_PROJECT, self.directory.replace(os.sep, '-'))
        self._load(host_arch, target_arch)
        profile_end(Topics.LOAD_PROJECT, self.directory.replace(os.sep, '-'))

    def translate_url(self, url):
        """Translates the given url which may be specified with an alias
        into a fully qualified url.

        Args:
           url (str): A url, which may be using an alias

        Returns:
           str: The fully qualified url, with aliases resolved

        This method is provided for :class:`.Source` objects to resolve
        fully qualified urls based on the shorthand which is allowed
        to be specified in the YAML
        """
        if url and _ALIAS_SEPARATOR in url:
            url_alias, url_body = url.split(_ALIAS_SEPARATOR, 1)
            alias_url = self._aliases.get(url_alias)
            if alias_url:
                url = alias_url + url_body

        return url

    # _load():
    #
    # Loads the project configuration file in the project directory
    # and extracts some things.
    #
    # Raises: LoadError if there was a problem with the project.conf
    #
    def _load(self, host_arch, target_arch):

        # Load builtin default
        projectfile = os.path.join(self.directory, "project.conf")
        config = _yaml.load(_site.default_project_config)

        # Special variables which have a computed default value must
        # be processed here before compositing any overrides
        variables = _yaml.node_get(config, Mapping, 'variables')
        variables['max-jobs'] = multiprocessing.cpu_count()

        variables['bst-host-arch'] = host_arch
        variables['bst-target-arch'] = target_arch

        # This is kept around for compatibility with existing definitions,
        # but we should probably remove it due to being ambiguous.
        variables['bst-arch'] = host_arch

        # Load project local config and override the builtin
        project_conf = _yaml.load(projectfile)
        _yaml.composite(config, project_conf, typesafe=True)

        # Resolve arches keyword, project may have arch conditionals
        _loader.resolve_arch(config, host_arch, target_arch)

        # The project name
        self.name = _yaml.node_get(config, str, 'name')

        # Load the plugin paths
        plugins = _yaml.node_get(config, Mapping, 'plugins', default_value={})
        self._plugin_source_paths = [os.path.join(self.directory, path)
                                     for path in self._extract_plugin_paths(plugins, 'sources')]
        self._plugin_element_paths = [os.path.join(self.directory, path)
                                      for path in self._extract_plugin_paths(plugins, 'elements')]

        # Resolve element base path
        elt_path = _yaml.node_get(config, str, 'element-path')
        self.element_path = os.path.join(self.directory, elt_path)

        # Source url aliases
        self._aliases = _yaml.node_get(config, Mapping, 'aliases', default_value={})

        # Load base variables
        self._variables = _yaml.node_get(config, Mapping, 'variables')

        # Load sandbox configuration
        self._environment = _yaml.node_get(config, Mapping, 'environment')
        self._env_nocache = _yaml.node_get(config, list, 'environment-nocache')

        # Load project split rules
        self._splits = _yaml.node_get(config, Mapping, 'split-rules')

        # Element configurations
        self._elements = _yaml.node_get(config, Mapping, 'elements', default_value={})

        # Workspace configurations
        self.__workspaces = self._load_workspace_config()

    # _workspaces()
    #
    # Generator function to enumerate workspaces.
    #
    # Yields:
    #    A tuple in the following format: (element, source, path).
    def _workspaces(self):
        for element in self.__workspaces:
            if element == _yaml.PROVENANCE_KEY:
                continue
            for source in self.__workspaces[element]:
                if source == _yaml.PROVENANCE_KEY:
                    continue
                yield (element, int(source), self.__workspaces[element][source])

    # _get_workspace()
    #
    # Get the path of the workspace source associated with the given
    # element's source at the given index
    #
    # Args:
    #    element (str) - The element name
    #    index (int) - The source index
    #
    # Returns:
    #    None if no workspace is open, the path to the workspace
    #    otherwise
    #
    def _get_workspace(self, element, index):
        try:
            return self.__workspaces[element][index]
        except KeyError:
            return None

    # _set_workspace()
    #
    # Set the path of the workspace associated with the given
    # element's source at the given index
    #
    # Args:
    #    element (str) - The element name
    #    index (int) - The source index
    #    path (str) - The path to set the workspace to
    #
    def _set_workspace(self, element, index, path):
        if element.name not in self.__workspaces:
            self.__workspaces[element.name] = {}

        self.__workspaces[element.name][index] = path
        element._set_source_workspace(index, path)

    # _delete_workspace()
    #
    # Remove the workspace from the workspace element. Note that this
    # does *not* remove the workspace from the stored yaml
    # configuration, call _save_workspace_config() afterwards.
    #
    # Args:
    #    element (str) - The element name
    #    index (int) - The source index
    #
    def _delete_workspace(self, element, index):
        del self.__workspaces[element][index]

        # Contains a provenance object
        if len(self.__workspaces[element]) == 1:
            del self.__workspaces[element]

    # _load_workspace_config()
    #
    # Load the workspace configuration and return a node containing
    # all open workspaces for the project
    #
    # Returns:
    #
    #    A node containing a dict that assigns projects to their
    #    workspaces. For example:
    #
    #        amhello.bst: {
    #            0: /home/me/automake,
    #            1: /home/me/amhello
    #        }
    #
    def _load_workspace_config(self):
        os.makedirs(os.path.join(self.directory, ".bst"), exist_ok=True)
        workspace_file = os.path.join(self.directory, ".bst", "workspaces.yml")
        try:
            open(workspace_file, "a").close()
        except IOError as e:
            raise LoadError(LoadErrorReason.MISSING_FILE,
                            "Could not load workspace config: {}".format(e)) from e

        return _yaml.load(workspace_file)

    # _save_workspace_config()
    #
    # Dump the current workspace element to the project configuration
    # file. This makes any changes performed with _delete_workspace or
    # _set_workspace permanent
    #
    def _save_workspace_config(self):
        _yaml.dump(_yaml.node_sanitize(self.__workspaces),
                   os.path.join(self.directory, ".bst", "workspaces.yml"))

    def _extract_plugin_paths(self, node, name):
        if not node:
            return
        path_list = _yaml.node_get(node, list, name, default_value=[])
        for i in range(len(path_list)):
            path = _yaml.node_get(node, str, name, indices=[i])
            yield path

    # _get_cache_key():
    #
    # Returns the cache key, calculating it if necessary
    #
    # Returns:
    #    (str): A hex digest cache key for the Context
    #
    def _get_cache_key(self):
        if self._cache_key is None:

            # Anything that alters the build goes into the unique key
            # (currently nothing here)
            self._cache_key = utils._generate_key({})

        return self._cache_key
