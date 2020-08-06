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

from .pluginorigin import PluginOrigin, PluginOriginType


# PluginOriginLocal
#
# PluginOrigin for local plugins
#
class PluginOriginLocal(PluginOrigin):
    def __init__(self):
        super().__init__(PluginOriginType.LOCAL)

        # Project relative path to where plugins from this origin are found
        self._path = None

    def get_plugin_paths(self, kind, plugin_type):
        path = os.path.join(self.project.directory, self._path)
        defaults = os.path.join(path, "{}.yaml".format(kind))
        if not os.path.exists(defaults):
            defaults = None

        return path, defaults, "project directory: {}".format(self._path)

    def load_config(self, origin_node):

        origin_node.validate_keys(["path", *PluginOrigin._COMMON_CONFIG_KEYS])

        path_node = origin_node.get_scalar("path")
        self._path = self.project.get_path_from_node(path_node, check_is_dir=True)
