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
from .._exceptions import PluginError

from .pluginorigin import PluginType, PluginOrigin, PluginOriginType


# PluginOriginJunction
#
# PluginOrigin for junction plugins
#
class PluginOriginJunction(PluginOrigin):
    def __init__(self):
        super().__init__(PluginOriginType.JUNCTION)

        # The junction element name through which to load plugins
        self._junction = None

    def get_plugin_paths(self, kind, plugin_type):

        # Get access to the project indicated by the junction,
        # possibly loading it as a side effect.
        #
        loader = self.project.loader.get_loader(self._junction, self.provenance_node)
        project = loader.project

        # Now get the appropriate PluginFactory object
        #
        if plugin_type == PluginType.SOURCE:
            factory = project.source_factory
        elif plugin_type == PluginType.ELEMENT:
            factory = project.element_factory

        # Now ask for the paths from the subproject PluginFactory
        try:
            location, defaults, display = factory.get_plugin_paths(kind)
        except PluginError as e:
            # Add some context to an error raised by loading a plugin from a subproject
            #
            raise PluginError(
                "{}: Error loading {} plugin '{}' from project '{}' referred to by junction '{}': {}".format(
                    self.provenance_node.get_provenance(), plugin_type, kind, project.name, self._junction, e
                ),
                reason="junction-plugin-load-error",
                detail=e.detail,
            ) from e

        if not location:
            # Raise a helpful error if the referred plugin type is not found in a subproject
            #
            # Note that this can also bubble up through the above error when looking for
            # a plugin from a subproject which in turn requires the same plugin from it's
            # subproject.
            #
            raise PluginError(
                "{}: project '{}' referred to by junction '{}' does not declare any {} plugin kind: '{}'".format(
                    self.provenance_node.get_provenance(), project.name, self._junction, plugin_type, kind
                ),
                reason="junction-plugin-not-found",
            )

        # Use the resolved project path for the display string rather than the user configured junction path
        project_path = "toplevel project"
        if project.junction:
            project_path = project.junction._get_full_name()

        return location, defaults, "junction: {} ({})".format(project_path, display)

    def load_config(self, origin_node):

        origin_node.validate_keys(["junction", *PluginOrigin._COMMON_CONFIG_KEYS])

        self._junction = origin_node.get_str("junction")
