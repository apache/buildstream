#
#  Copyright (C) 2020 Codethink Limited
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

import os

from ..types import FastEnum
from ..node import ScalarNode, MappingNode
from .._exceptions import LoadError
from ..exceptions import LoadErrorReason


# PluginOriginType:
#
# An enumeration depicting the type of plugin origin
#
class PluginOriginType(FastEnum):
    LOCAL = "local"
    PIP = "pip"


# PluginConfiguration:
#
# An object representing the configuration of a single
# plugin in the origin.
#
class PluginConfiguration:
    def __init__(self, kind, allow_deprecated):
        self.kind = kind
        self.allow_deprecated = allow_deprecated


# PluginOrigin
#
# Base class holding common properties of all origins.
#
class PluginOrigin:

    # Common fields valid for all plugin origins
    _COMMON_CONFIG_KEYS = ["origin", "sources", "elements", "allow-deprecated"]

    def __init__(self, origin_type):

        # Public
        self.origin_type = origin_type  # The PluginOriginType
        self.elements = {}  # A dictionary of PluginConfiguration
        self.sources = {}  # A dictionary of PluginConfiguration objects
        self.provenance = None

        # Private
        self._project = None
        self._kinds = {}
        self._allow_deprecated = False

    # new_from_node()
    #
    # Load a PluginOrigin from the YAML in project.conf
    #
    # Args:
    #    project (Project): The project from whence this origin is loaded
    #    origin_node (MappingNode): The node defining this origin
    #
    # Returns:
    #    (PluginOrigin): The newly created PluginOrigin
    #
    @classmethod
    def new_from_node(cls, project, origin_node):

        origin_type = origin_node.get_enum("origin", PluginOriginType)

        if origin_type == PluginOriginType.LOCAL:
            origin = PluginOriginLocal()
        elif origin_type == PluginOriginType.PIP:
            origin = PluginOriginPip()

        origin.provenance = origin_node.get_provenance()
        origin._project = project
        origin._load(origin_node)

        # Parse commonly defined aspects of PluginOrigins
        origin._allow_deprecated = origin_node.get_bool("allow-deprecated", False)

        element_sequence = origin_node.get_sequence("elements", [])
        origin._load_plugin_configurations(element_sequence, origin.elements)

        source_sequence = origin_node.get_sequence("sources", [])
        origin._load_plugin_configurations(source_sequence, origin.sources)

        return origin

    # _load()
    #
    # Abstract method for loading data from the origin node, this
    # method should not load the source and element lists.
    #
    # Args:
    #    origin_node (MappingNode): The node defining this origin
    #
    def _load(self, origin_node):
        pass

    # _load_plugin_configurations()
    #
    # Helper function to load the list of source or element
    # PluginConfigurations
    #
    # Args:
    #    sequence_node (SequenceNode): The list of configurations
    #    dictionary (dict): The location to store the results
    #
    def _load_plugin_configurations(self, sequence_node, dictionary):

        for node in sequence_node:

            # Parse as a simple string
            if type(node) is ScalarNode:  # pylint: disable=unidiomatic-typecheck
                kind = node.as_str()
                conf = PluginConfiguration(kind, self._allow_deprecated)

            # Parse as a dictionary
            elif type(node) is MappingNode:  # pylint: disable=unidiomatic-typecheck
                node.validate_keys(["kind", "allow-deprecated"])
                kind = node.get_str("kind")
                allow_deprecated = node.get_bool("allow-deprecated", self._allow_deprecated)
                conf = PluginConfiguration(kind, allow_deprecated)
            else:
                p = node.get_provenance()
                raise LoadError(
                    "{}: Plugin is not specified as a string or a dictionary".format(p), LoadErrorReason.INVALID_DATA
                )

            dictionary[kind] = conf


# PluginOriginLocal
#
# PluginOrigin for local plugins
#
class PluginOriginLocal(PluginOrigin):
    def __init__(self):
        super().__init__(PluginOriginType.LOCAL)

        # An absolute path to where the plugin can be found
        #
        self.path = None

    def _load(self, origin_node):

        origin_node.validate_keys(["path", *PluginOrigin._COMMON_CONFIG_KEYS])

        path_node = origin_node.get_scalar("path")
        path = self._project.get_path_from_node(path_node, check_is_dir=True)

        self.path = os.path.join(self._project.directory, path)


# PluginOriginPip
#
# PluginOrigin for pip plugins
#
class PluginOriginPip(PluginOrigin):
    def __init__(self):
        super().__init__(PluginOriginType.PIP)

        # The pip package name to extract plugins from
        #
        self.package_name = None

    def _load(self, origin_node):

        origin_node.validate_keys(["package-name", *PluginOrigin._COMMON_CONFIG_KEYS])
        self.package_name = origin_node.get_str("package-name")
