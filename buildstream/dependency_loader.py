#
#  Copyright (C) 2019 Codethink Limited
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
#        Valentin David <valentin.david@codethink.co.uk>
"""
Dependency Loader
=================

A dependency loader can extract extra dependencies from an element
configuration. In this case, An :class:`Element
<buildstream.element.Element>` will define a class member
`DEPENDENCY_LOADER` to a class implementing :class:`DependencyLoader
<buildstream.dependency_loader.DependencyLoader>`.

This :class:`DependencyLoader
<buildstream.dependency_loader.DependencyLoader>` will provide through
implementation of :func:`DependencyLoader.get_dependencies
<buildstream.dependency_loader.DependencyLoader.get_dependencies>` a
list of :class:`Dependency
<buildstream.dependency_loader.Dependency>`.

Class Reference
---------------

"""

import os
from collections.abc import Mapping

from . import _yaml

from .plugin import Plugin
from ._exceptions import LoadError, LoadErrorReason, ImplError


class Dependency():

    """Dependency()

    A simple object describing a dependency

    Args:
       name (str): The element name
       dep_type (str): The type of dependency, can be
                       Symbol.ALL, Symbol.BUILD, or Symbol.RUNTIME
       junction (str): The element name of the junction, or None
       provenance (Provenance): The YAML node provenance of where this
                                dependency was declared
    """

    def __init__(self, name,
                 dep_type=None, junction=None, provenance=None):
        self.name = name
        assert dep_type in (None, 'build', 'runtime', 'all')
        self.dep_type = dep_type
        self.junction = junction
        self.provenance = provenance


class DependencyLoader(Plugin):

    """DependencyLoader()

    Base class for element dependency loaders.
    """

    def __init__(self, name, context, project, default_conf):

        super().__init__(name, context, project, None, "dependency_loader")

        defaults = {}
        try:
            defaults = _yaml.load(default_conf, os.path.basename(default_conf))
        except LoadError as e:
            if e.reason != LoadErrorReason.MISSING_FILE:
                raise e

        elements = project.element_overrides
        overrides = elements.get(self.get_kind())
        if overrides:
            _yaml.composite(defaults, overrides)

        self.__defaults = defaults

    def get_dependencies(self, node):
        """Return the list of extra dependencies given a configuration node

        Args:
           node (dict): The configuration node

        Returns:
           (list of Dependency): The extra dependencies found

        This is an abstract method. Implementations of
        DependencyLoader are required to implement this method.
        """
        raise ImplError("DependencyLoader plugin for element '{kind}' does not implement get_dependencies()".format(
            kind=self.get_kind()))

    # _get_dependencies()
    #
    # Get dependencies given a raw config node
    #
    # Args:
    #    node (dict): The configuration node
    #
    # Returns:
    #    (list of Dependency): The extra dependencies found
    #
    # This method will call DependencyLoader.get_dependencies()
    # after applying default configuration for the plugin. The
    # defaults come from the corresponding element plugin.
    def _get_dependencies(self, node):

        default_config = _yaml.node_get(self.__defaults, Mapping, 'config', default_value={})
        default_config = _yaml.node_chain_copy(default_config)
        _yaml.composite(default_config, node)

        return self.get_dependencies(default_config)
