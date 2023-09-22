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
#  Authors:
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

from typing import TYPE_CHECKING, Type, cast

from .pluginfactory import PluginFactory
from .pluginorigin import PluginType

from ..node import MappingNode
from ..plugin import Plugin
from ..sourcemirror import SourceMirror

if TYPE_CHECKING:
    from .._context import Context
    from .._project import Project


# A SourceMirrorFactory creates SourceMirror instances
# in the context of a given factory
#
# Args:
#     plugin_base (PluginBase): The main PluginBase object to work with
#
class SourceMirrorFactory(PluginFactory):
    def __init__(self, plugin_base):
        super().__init__(plugin_base, PluginType.SOURCE_MIRROR)

    # create():
    #
    # Create a SourceMirror object.
    #
    # Args:
    #    context (object): The Context object for processing
    #    project (object): The project object
    #    node (MappingNode): The node where the mirror was defined
    #
    # Returns:
    #    A newly created SourceMirror object of the appropriate kind
    #
    # Raises:
    #    PluginError (if the kind lookup failed)
    #    LoadError (if the source mirror itself took issue with the config)
    #
    def create(self, context: "Context", project: "Project", node: MappingNode) -> SourceMirror:
        plugin_type: Type[Plugin]

        # Shallow parsing to get the custom plugin type, delegate the remainder
        # of the parsing to SourceMirror
        #
        kind = node.get_str("kind", "default")

        plugin_type, _ = self.lookup(context.messenger, kind, node)

        source_mirror_type = cast(Type[SourceMirror], plugin_type)
        source_mirror = source_mirror_type(context, project, node)
        return source_mirror
