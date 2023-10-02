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
from .._loader import LoadElement
from ..element import Element

if TYPE_CHECKING:
    from .._context import Context
    from .._project import Project


# A ElementFactory creates Element instances
# in the context of a given factory
#
# Args:
#     plugin_base (PluginBase): The main PluginBase object to work with
#
class ElementFactory(PluginFactory):
    def __init__(self, plugin_base):
        super().__init__(plugin_base, PluginType.ELEMENT)

    # create():
    #
    # Create an Element object.
    #
    # Args:
    #    context (object): The Context object for processing
    #    project (object): The project object
    #    load_element (object): The LoadElement
    #
    # Returns: A newly created Element object of the appropriate kind
    #
    # Raises:
    #    PluginError (if the kind lookup failed)
    #    LoadError (if the element itself took issue with the config)
    #
    def create(self, context: "Context", project: "Project", load_element: LoadElement) -> Element:
        plugin_type, default_config = self.lookup(context.messenger, load_element.kind, load_element.node)
        element_type = cast(Type[Element], plugin_type)
        element = element_type(context, project, load_element, default_config)
        return element
