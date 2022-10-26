#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
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
