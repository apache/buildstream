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
from ..source import Source
from .._loader import MetaSource
from .._variables import Variables

if TYPE_CHECKING:
    from .._context import Context
    from .._project import Project


# A SourceFactory creates Source instances
# in the context of a given factory
#
# Args:
#     plugin_base (PluginBase): The main PluginBase object to work with
#
class SourceFactory(PluginFactory):
    def __init__(self, plugin_base):
        super().__init__(plugin_base, PluginType.SOURCE)

    # create():
    #
    # Create a Source object.
    #
    # Args:
    #    context (object): The Context object for processing
    #    project (object): The project object
    #    meta (object): The loaded MetaSource
    #    variables (Variables): The variables available to the source
    #
    # Returns:
    #    A newly created Source object of the appropriate kind
    #
    # Raises:
    #    PluginError (if the kind lookup failed)
    #    LoadError (if the source itself took issue with the config)
    #
    def create(self, context: "Context", project: "Project", meta: MetaSource, variables: Variables) -> Source:
        plugin_type, _ = self.lookup(context.messenger, meta.kind, meta.config)
        source_type = cast(Type[Source], plugin_type)
        source = source_type(context, project, meta, variables)
        return source
