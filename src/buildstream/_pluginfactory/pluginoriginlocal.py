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
