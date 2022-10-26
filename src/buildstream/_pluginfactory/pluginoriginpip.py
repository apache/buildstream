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

        import pkg_resources

        # Sources and elements are looked up in separate
        # entrypoint groups from the same package.
        #
        if plugin_type == PluginType.SOURCE:
            entrypoint_group = "buildstream.plugins.sources"
        elif plugin_type == PluginType.ELEMENT:
            entrypoint_group = "buildstream.plugins.elements"

        # key by a tuple to avoid collision
        try:
            package = pkg_resources.get_entry_info(self._package_name, entrypoint_group, kind)
        except pkg_resources.DistributionNotFound as e:
            raise PluginError(
                "{}: Failed to load {} plugin '{}': {}".format(
                    self.provenance_node.get_provenance(), plugin_type, kind, e
                ),
                reason="package-not-found",
            ) from e
        except pkg_resources.VersionConflict as e:
            raise PluginError(
                "{}: Version conflict encountered while loading {} plugin '{}'".format(
                    self.provenance_node.get_provenance(), plugin_type, kind
                ),
                detail=e.report(),
                reason="package-version-conflict",
            ) from e
        except (
            # For setuptools < 49.0.0
            pkg_resources.RequirementParseError,
            # For setuptools >= 49.0.0
            pkg_resources.extern.packaging.requirements.InvalidRequirement,
        ) as e:
            raise PluginError(
                "{}: Malformed package-name '{}' encountered: {}".format(
                    self.provenance_node.get_provenance(), self._package_name, e
                ),
                reason="package-malformed-requirement",
            ) from e

        if package is None:
            raise PluginError(
                "{}: Pip package {} does not contain a plugin named '{}'".format(
                    self.provenance_node.get_provenance(), self._package_name, kind
                ),
                reason="plugin-not-found",
            )

        location = package.dist.get_resource_filename(
            pkg_resources._manager, package.module_name.replace(".", os.sep) + ".py"
        )

        # Also load the defaults - required since setuptools
        # may need to extract the file.
        try:
            defaults = package.dist.get_resource_filename(
                pkg_resources._manager, package.module_name.replace(".", os.sep) + ".yaml"
            )
        except KeyError:
            # The plugin didn't have an accompanying YAML file
            defaults = None

        return (
            os.path.dirname(location),
            defaults,
            "python package '{}' at: {}".format(package.dist, package.dist.location),
        )

    def load_config(self, origin_node):

        origin_node.validate_keys(["package-name", *PluginOrigin._COMMON_CONFIG_KEYS])
        self._package_name = origin_node.get_str("package-name")
