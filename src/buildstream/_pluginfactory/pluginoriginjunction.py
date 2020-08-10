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
        loader = self.project.loader.get_loader(self._junction, self.provenance)
        project = loader.project
        project.ensure_fully_loaded()

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
                    self.provenance, plugin_type, kind, project.name, self._junction, e
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
                    self.provenance, project.name, self._junction, plugin_type, kind
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
