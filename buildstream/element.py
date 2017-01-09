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

import os
import copy
import inspect
from enum import Enum

from . import _yaml
from ._variables import Variables
from . import ImplError, LoadError, LoadErrorReason
from . import Plugin
from . import utils


class Scope(Enum):
    """Types of scope for a given element"""

    ALL = 1
    """All elements which the given element depends on, following
    all elements required for building. Including the element itself.
    """

    BUILD = 2
    """All elements required for building the element, including their
    respective run dependencies. Not including the given element itself.
    """

    RUN = 3
    """All elements required for running the element. Including the element
    itself.
    """


class Element(Plugin):
    """Element()

    Base Element class.

    All elements derive from this class, this interface defines how
    the core will be interacting with Elements.
    """
    __defaults = {}          # The defaults from the yaml file and project
    __defaults_set = False   # Flag, in case there are no defaults at all

    def __init__(self, context, project, meta):
        provenance = _yaml.node_get_provenance(meta.config)
        super().__init__(context, project, provenance, "element")

        self.name = meta.name
        """The element name"""

        self.__runtime_dependencies = []
        self.__build_dependencies = []
        self.__sources = []
        self.__cache_key = None

        self.__init_defaults()

        # Collect the composited environment
        env = self.__extract_environment(meta)
        self.__environment = env

        # Collect the composited variables and resolve them
        variables = self.__extract_variables(meta)
        self.__variables = Variables(variables)

        # Collect the composited element configuration and
        # ask the element to configure itself.
        config = self.__extract_config(meta)
        self.configure(config)

    def dependencies(self, scope, mask=None):
        """dependencies(scope)

        A generator function which lists the dependencies of the given element
        deterministically, starting with the basemost elements in the given scope.

        Args:
           scope (:class:`.Scope`): The scope to iterate in

        Returns:
           (list): The dependencies in *scope*, in deterministic staging order
        """

        # A little reentrancy protection, this loop could be
        # optimized but not bothering at this point.
        #
        if mask is None:
            mask = []
        if self.name in mask:
            return
        mask.append(self.name)

        if scope == Scope.ALL:
            for dep in self.__build_dependencies:
                for elt in dep.dependencies(Scope.ALL, mask=mask):
                    yield elt
            for dep in self.__runtime_dependencies:
                if dep not in self.__build_dependencies:
                    for elt in dep.dependencies(Scope.ALL, mask=mask):
                        yield elt

        elif scope == Scope.BUILD:
            for dep in self.__build_dependencies:
                for elt in dep.dependencies(Scope.RUN, mask=mask):
                    yield elt

        elif scope == Scope.RUN:
            for dep in self.__runtime_dependencies:
                for elt in dep.dependencies(Scope.RUN, mask=mask):
                    yield elt

        # Yeild self only at the end, after anything needed has been traversed
        if (scope == Scope.ALL or scope == Scope.RUN):
            yield self

    def node_subst_member(self, node, member_name, default_value=None):
        """Fetch the value of a string node member, substituting any variables
        in the loaded value with the element contextual variables.

        Args:
           node (dict): A dictionary loaded from YAML
           member_name (str): The name of the member to fetch
           default_value (str): A value to return when *member_name* is not specified in *node*

        Returns:
           The value of *member_name* in *node*, otherwise *default_value*

        Raises:
           :class:`.LoadError`: When *member_name* is not found and no *default_value* was provided

        This is essentially the same as :func:`~buildstream.plugin.Plugin.node_get_member`
        except that it assumes the expected type is a string and will also perform variable
        substitutions.

        **Example:**

        .. code:: python

          # Expect a string 'name' in 'node', substituting any
          # variables in the returned string
          name = self.node_subst_member(node, 'name')
        """
        value = self.node_get_member(node, str, member_name, default_value=default_value)
        return self.__variables.subst(value)

    def node_subst_list_element(self, node, member_name, indices):
        """Fetch the value of a list element from a node member, substituting any variables
        in the loaded value with the element contextual variables.

        Args:
           node (dict): A dictionary loaded from YAML
           member_name (str): The name of the member to fetch
           indices (list of int): List of indices to search, in case of nested lists

        Returns:
           The value of the list element in *member_name* at the specified *indices*

        Raises:
           :class:`.LoadError`

        This is essentially the same as :func:`~buildstream.plugin.Plugin.node_get_list_element`
        except that it assumes the expected type is a string and will also perform variable
        substitutions.

        **Example:**

        .. code:: python

          # Fetch the list itself
          strings = self.node_get_member(node, list, 'strings')

          # Iterate over the list indices
          for i in range(len(strings)):

              # Fetch the strings in this list, substituting content
              # with our element's variables if needed
              string = self.node_subst_list_element(
                  node, 'strings', [ i ])
        """
        value = self.node_get_list_element(node, str, member_name, indices)
        return self.__variables.subst(value)

    #############################################################
    #            Private Methods used in BuildStream            #
    #############################################################

    # _inconsistent():
    #
    # Returns:
    #    (list): A list of inconsistent sources
    #
    def _inconsistent(self):
        return [source for source in self.__sources if not source.consistent()]

    # _get_cache_key():
    #
    # Returns the cache key, calculating it if necessary
    #
    # Returns:
    #    (str): A hex digest cache key for this Element
    #
    def _get_cache_key(self):
        if self.__cache_key is None:
            context = self.get_context()
            self.__cache_key = utils._generate_key({
                'context': context._get_cache_key(),
                'element': self.get_unique_key(),
                'sources': [s.get_unique_key() for s in self.__sources],
                'dependencies': [e._get_cache_key() for e in self.dependencies(Scope.BUILD)],
            })

        return self.__cache_key

    # _refresh():
    #
    # Calls refresh on the Element sources
    #
    # Raises:
    #    SourceError: If one of the element sources has an error
    #
    # Returns:
    #    (dict): A mapping of filenames and toplevel yaml nodes which
    #            need to be saved
    #    (list): A list of Source objects which changed
    #
    def _refresh(self):
        files = {}
        changed = []

        for source in self.__sources:
            if source.refresh(source._Source__origin_node):
                files[source._Source__origin_filename] = source._Source__origin_toplevel
                changed.append(source)

        return files, changed

    #############################################################
    #                   Private Local Methods                   #
    #############################################################
    def __init_defaults(self):

        # Defaults are loaded once per class and then reused
        #
        if not self.__defaults_set:

            # Get the yaml file in the same directory as the plugin
            plugin_file = inspect.getfile(type(self))
            plugin_dir = os.path.dirname(plugin_file)
            plugin_conf_name = "%s.yaml" % self.get_kind()
            plugin_conf = os.path.join(plugin_dir, "%s.yaml" % self.get_kind())

            # Override some plugin defaults with project overrides
            #
            defaults = {}
            project = self.get_project()
            elements = project._elements
            overrides = elements.get(self.get_kind())

            try:
                defaults = _yaml.load(plugin_conf, plugin_conf_name)
                if overrides:
                    _yaml.composite(defaults, overrides, typesafe=True)
            except LoadError as e:
                # Ignore missing file errors, element's may omit a config file.
                if e.reason == LoadErrorReason.MISSING_FILE:
                    if overrides:
                        defaults = copy.deepcopy(overrides)
                else:
                    raise e

            # Set the data class wide
            type(self).__defaults = defaults
            self.__defaults_set = True

    # This will resolve the final environment to be used when
    # creating sandboxes for this element
    #
    def __extract_environment(self, meta):
        project = self.get_project()
        default_env = _yaml.node_get(self.__defaults, dict, 'environment', default_value={})
        element_env = meta.environment

        # Overlay default_env with element_env
        default_env = copy.deepcopy(default_env)
        _yaml.composite(default_env, element_env, typesafe=True)
        element_env = default_env

        # Overlay base_env with element_env
        base_env = copy.deepcopy(project._environment)
        _yaml.composite(base_env, element_env, typesafe=True)
        element_env = base_env

        return element_env

    # This will resolve the final variables to be used when
    # substituting command strings to be run in the sandbox
    #
    def __extract_variables(self, meta):
        project = self.get_project()
        default_vars = _yaml.node_get(self.__defaults, dict, 'variables', default_value={})
        element_vars = meta.variables

        # Overlay default_vars with element_vars
        default_vars = copy.deepcopy(default_vars)
        _yaml.composite(default_vars, element_vars, typesafe=True)
        element_vars = default_vars

        # Overlay base_vars with element_vars
        base_vars = copy.deepcopy(project._variables)
        _yaml.composite(base_vars, element_vars, typesafe=True)
        element_vars = base_vars

        return element_vars

    # This will resolve the final configuration to be handed
    # off to element.configure()
    #
    def __extract_config(self, meta):

        # The default config is already composited with the project overrides
        default_config = _yaml.node_get(self.__defaults, dict, 'config', default_value={})
        element_config = meta.config

        default_config = copy.deepcopy(default_config)
        _yaml.composite(default_config, element_config, typesafe=True)
        element_config = default_config

        return element_config
