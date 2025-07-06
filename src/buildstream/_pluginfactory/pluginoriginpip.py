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
import sys

from .._exceptions import PluginError

from .pluginorigin import PluginType, PluginOrigin, PluginOriginType


# PluginOriginPip
#
# PluginOrigin for pip plugins
#
class PluginOriginPip(PluginOrigin):
    def __init__(self):
        super().__init__(PluginOriginType.PIP)

        # The pip package name to extract plugins from
        #
        self._package_name = None

    def get_plugin_paths(self, kind, plugin_type):

        from packaging.requirements import Requirement, InvalidRequirement

        if sys.version_info >= (3, 10):
            from importlib.metadata import distribution, PackageNotFoundError
        else:
            from importlib_metadata import distribution, PackageNotFoundError

        # Sources and elements are looked up in separate
        # entrypoint groups from the same package.
        #
        if plugin_type == PluginType.SOURCE:
            entrypoint_group = "buildstream.plugins.sources"
        elif plugin_type == PluginType.ELEMENT:
            entrypoint_group = "buildstream.plugins.elements"
        elif plugin_type == PluginType.SOURCE_MIRROR:
            entrypoint_group = "buildstream.plugins.sourcemirrors"
        else:
            assert False, "unreachable"

        try:
            package = Requirement(self._package_name)
        except InvalidRequirement as e:
            raise PluginError(
                "{}: Malformed package-name '{}' encountered: {}".format(
                    self.provenance_node.get_provenance(), self._package_name, e
                ),
                reason="package-malformed-requirement",
            ) from e

        try:
            dist = distribution(package.name)
        except PackageNotFoundError as e:
            raise PluginError(
                "{}: Failed to load {} plugin '{}': {}".format(
                    self.provenance_node.get_provenance(), plugin_type, kind, e
                ),
                reason="package-not-found",
            ) from e

        if not package.specifier.contains(dist.version, prereleases=True):
            raise PluginError(
                "{}: Version conflict encountered while loading {} plugin '{}'".format(
                    self.provenance_node.get_provenance(), plugin_type, kind
                ),
                detail="{} {} is installed but {} is required".format(dist.name, dist.version, package),
                reason="package-version-conflict",
            )

        try:
            entrypoint = dist.entry_points.select(group=entrypoint_group)[kind]
        except KeyError as e:
            raise PluginError(
                "{}: Pip package {} does not contain a {} plugin named '{}'".format(
                    self.provenance_node.get_provenance(), self._package_name, plugin_type, kind
                ),
                reason="plugin-not-found",
            )

        location = dist.locate_file(entrypoint.module.replace(".", os.sep) + ".py")
        defaults = dist.locate_file(entrypoint.module.replace(".", os.sep) + ".yaml")

        if not defaults.exists():
            # The plugin didn't have an accompanying YAML file
            defaults = None

        return (
            os.path.dirname(location),
            str(defaults),
            "python package '{}' at: {}".format(dist, dist.locate_file("")),
        )

    def load_config(self, origin_node):

        origin_node.validate_keys(["package-name", *PluginOrigin._COMMON_CONFIG_KEYS])
        self._package_name = origin_node.get_str("package-name")
