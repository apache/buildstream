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

from .pluginorigin import PluginOrigin, PluginOriginType, PluginType
from .pluginoriginlocal import PluginOriginLocal
from .pluginoriginpip import PluginOriginPip
from .pluginoriginjunction import PluginOriginJunction
from .sourcefactory import SourceFactory
from .elementfactory import ElementFactory


# load_plugin_origin()
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
def load_plugin_origin(project, origin_node):

    origin_type = origin_node.get_enum("origin", PluginOriginType)

    if origin_type == PluginOriginType.LOCAL:
        origin = PluginOriginLocal()
    elif origin_type == PluginOriginType.PIP:
        origin = PluginOriginPip()
    elif origin_type == PluginOriginType.JUNCTION:
        origin = PluginOriginJunction()

    origin.initialize(project, origin_node)

    return origin
