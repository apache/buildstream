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

from .pluginfactory import PluginFactory
from .pluginorigin import PluginType


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
    # Create an Element object, the pipeline uses this to create Element
    # objects on demand for a given pipeline.
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
    def create(self, context, project, load_element):
        element_type, default_config = self.lookup(context.messenger, load_element.kind, load_element.node)
        element = element_type(context, project, load_element, default_config)
        return element
