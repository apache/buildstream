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

from ..types import FastEnum
from ..node import ScalarNode, MappingNode
from .._exceptions import LoadError
from ..exceptions import LoadErrorReason


# PluginType()
#
# A type of plugin
#
class PluginType(FastEnum):

    # A Source plugin
    SOURCE = "source"

    # An Element plugin
    ELEMENT = "element"

    def __str__(self):
        return str(self.value)


# PluginOriginType:
#
# An enumeration depicting the type of plugin origin
#
class PluginOriginType(FastEnum):

    # A local plugin
    LOCAL = "local"

    # A pip plugin
    PIP = "pip"

    # A plugin loaded via a junction
    JUNCTION = "junction"


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
        self.project = None

        # Private
        self._kinds = {}
        self._allow_deprecated = False

    # initialize()
    #
    # Initializes the origin, resulting in loading the origin
    # node.
    #
    # This is the bottom half of the initialization, it is done
    # separately because load_plugin_origin() needs to stay in
    # __init__.py in order to avoid cyclic dependencies between
    # PluginOrigin and it's subclasses.
    #
    # Args:
    #    project (Project): The project this PluginOrigin was loaded for
    #    origin_node (MappingNode): The node defining this origin
    #
    def initialize(self, project, origin_node):

        self.provenance = origin_node.get_provenance()
        self.project = project
        self.load_config(origin_node)

        # Parse commonly defined aspects of PluginOrigins
        self._allow_deprecated = origin_node.get_bool("allow-deprecated", False)

        element_sequence = origin_node.get_sequence("elements", [])
        self._load_plugin_configurations(element_sequence, self.elements)

        source_sequence = origin_node.get_sequence("sources", [])
        self._load_plugin_configurations(source_sequence, self.sources)

    ##############################################
    #              Abstract methods              #
    ##############################################

    # get_plugin_paths():
    #
    # Abstract method for loading the details about a specific plugin,
    # the PluginFactory uses this to get the assets needed to actually
    # load the plugins.
    #
    # Args:
    #    kind (str): The plugin
    #    plugin_type (PluginType): The kind of plugin to load
    #
    # Returns:
    #    (str): The full path to the directory containing the plugin
    #    (str): The full path to the accompanying .yaml file containing
    #           the plugin's preferred defaults.
    #    (str): The explanatory display string describing how this plugin was loaded
    #
    def get_plugin_paths(self, kind, plugin_type):
        pass

    # load_config()
    #
    # Abstract method for loading data from the origin node, this
    # method should not load the source and element lists.
    #
    # Args:
    #    origin_node (MappingNode): The node defining this origin
    #
    def load_config(self, origin_node):
        pass

    ##############################################
    #               Private methods              #
    ##############################################

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
