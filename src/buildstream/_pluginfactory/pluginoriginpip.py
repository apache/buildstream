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
                "{}: Failed to load {} plugin '{}': {}".format(self.provenance, plugin_type, kind, e),
                reason="package-not-found",
            ) from e
        except pkg_resources.VersionConflict as e:
            raise PluginError(
                "{}: Version conflict encountered while loading {} plugin '{}'".format(
                    self.provenance, plugin_type, kind
                ),
                detail=e.report(),
                reason="package-version-conflict",
            ) from e
        except pkg_resources.RequirementParseError as e:
            raise PluginError(
                "{}: Malformed package-name '{}' encountered: {}".format(self.provenance, self._package_name, e),
                reason="package-malformed-requirement",
            ) from e

        if package is None:
            raise PluginError(
                "{}: Pip package {} does not contain a plugin named '{}'".format(
                    self.provenance, self._package_name, kind
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
