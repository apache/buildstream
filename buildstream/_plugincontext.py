#!/usr/bin/env python3
#
#  Copyright (C) 2016 Codethink Limited
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
#  Authors:
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

import os
import inspect

from ._exceptions import PluginError
from . import utils


# A Context for loading plugin types
#
# Args:
#     plugin_base (PluginBase): The main PluginBase object to work with
#     base_type (type):         A base object type for this context
#     site_plugin_path (str):   Path to where buildstream keeps plugins
#     plugin_origins (list):    Data used to search for plugins
#
# Since multiple pipelines can be processed recursively
# within the same interpretor, it's important that we have
# one context associated to the processing of a given pipeline,
# this way sources and element types which are particular to
# a given BuildStream project are isolated to their respective
# Pipelines.
#
class PluginContext():

    def __init__(self, plugin_base, base_type, site_plugin_path, plugin_origins=None, dependencies=None):

        self.dependencies = dependencies
        self.loaded_dependencies = []
        self.base_type = base_type  # The base class plugins derive from
        self.types = {}             # Plugin type lookup table by kind
        self.plugin_origins = plugin_origins or []

        # The PluginSource object
        self.plugin_base = plugin_base
        self.site_source = plugin_base.make_plugin_source(searchpath=site_plugin_path)
        self.alternate_sources = {}

    # lookup():
    #
    # Fetches a type loaded from a plugin in this plugin context
    #
    # Args:
    #     kind (str): The kind of Plugin to create
    #
    # Returns: the type associated with the given kind
    #
    # Raises: PluginError
    #
    def lookup(self, kind):
        return self.ensure_plugin(kind)

    def _get_local_plugin_source(self, path):
        if ('local', path) not in self.alternate_sources:
            # key by a tuple to avoid collision
            source = self.plugin_base.make_plugin_source(searchpath=[path])
            # Ensure that sources never get garbage collected,
            # as they'll take the plugins with them.
            self.alternate_sources[('local', path)] = source
        else:
            source = self.alternate_sources(('local', path))
        return source

    def _get_pip_plugin_source(self, package_name, kind):
        defaults = None
        if ('pip', package_name) not in self.alternate_sources:
            import pkg_resources
            # key by a tuple to avoid collision
            try:
                package = pkg_resources.get_entry_info(package_name,
                                                       'buildstream.plugins',
                                                       kind)
            except pkg_resources.DistributionNotFound as e:
                raise PluginError("Failed to load {} plugin '{}': {}"
                                  .format(self.base_type.__name__, kind, e)) from e
            location = package.dist.get_resource_filename(
                pkg_resources._manager,
                package.module_name.replace('.', os.sep) + '.py'
            )

            # Also load the defaults - required since setuptools
            # may need to extract the file.
            try:
                defaults = package.dist.get_resource_filename(
                    pkg_resources._manager,
                    package.module_name.replace('.', os.sep) + '.yaml'
                )
            except KeyError:
                # The plugin didn't have an accompanying YAML file
                defaults = None

            source = self.plugin_base.make_plugin_source(searchpath=[os.path.dirname(location)])
            self.alternate_sources[('pip', package_name)] = source

        else:
            source = self.alternate_sources[('pip', package_name)]

        return source, defaults

    def ensure_plugin(self, kind):

        if kind not in self.types:
            # Check whether the plugin is specified in plugins
            source = None
            defaults = None
            loaded_dependency = False
            for origin in self.plugin_origins:
                if kind not in origin['plugins']:
                    continue

                if origin['origin'] == 'local':
                    source = self._get_local_plugin_source(origin['path'])
                elif origin['origin'] == 'pip':
                    source, defaults = self._get_pip_plugin_source(origin['package-name'], kind)
                else:
                    raise PluginError("Failed to load plugin '{}': "
                                      "Unexpected plugin origin '{}'"
                                      .format(kind, origin['origin']))
                loaded_dependency = True
                break

            # Fall back to getting the source from site
            if not source:
                if kind not in self.site_source.list_plugins():
                    raise PluginError("No {} type registered for kind '{}'"
                                      .format(self.base_type.__name__, kind))

                source = self.site_source

            self.types[kind] = self.load_plugin(source, kind, defaults)
            if loaded_dependency:
                self.loaded_dependencies.append(kind)

        return self.types[kind]

    def load_plugin(self, source, kind, defaults):

        try:
            plugin = source.load_plugin(kind)

            if not defaults:
                plugin_file = inspect.getfile(plugin)
                plugin_dir = os.path.dirname(plugin_file)
                plugin_conf_name = "{}.yaml".format(kind)
                defaults = os.path.join(plugin_dir, plugin_conf_name)

        except ImportError as e:
            raise PluginError("Failed to load {} plugin '{}': {}"
                              .format(self.base_type.__name__, kind, e)) from e

        try:
            plugin_type = plugin.setup()
        except AttributeError as e:
            raise PluginError("{} plugin '{}' did not provide a setup() function"
                              .format(self.base_type.__name__, kind)) from e
        except TypeError as e:
            raise PluginError("setup symbol in {} plugin '{}' is not a function"
                              .format(self.base_type.__name__, kind)) from e

        self.assert_plugin(kind, plugin_type)
        self.assert_version(kind, plugin_type)
        return (plugin_type, defaults)

    def assert_plugin(self, kind, plugin_type):
        if kind in self.types:
            raise PluginError("Tried to register {} plugin for existing kind '{}' "
                              "(already registered {})"
                              .format(self.base_type.__name__, kind, self.types[kind].__name__))
        try:
            if not issubclass(plugin_type, self.base_type):
                raise PluginError("{} plugin '{}' returned type '{}', which is not a subclass of {}"
                                  .format(self.base_type.__name__, kind,
                                          plugin_type.__name__,
                                          self.base_type.__name__))
        except TypeError as e:
            raise PluginError("{} plugin '{}' returned something that is not a type (expected subclass of {})"
                              .format(self.base_type.__name__, kind,
                                      self.base_type.__name__)) from e

    def assert_version(self, kind, plugin_type):

        # Now assert BuildStream version
        bst_major, bst_minor = utils.get_bst_version()

        if bst_major < plugin_type.BST_REQUIRED_VERSION_MAJOR or \
           (bst_major == plugin_type.BST_REQUIRED_VERSION_MAJOR and
            bst_minor < plugin_type.BST_REQUIRED_VERSION_MINOR):
            raise PluginError("BuildStream {}.{} is too old for {} plugin '{}' (requires {}.{})"
                              .format(
                                  bst_major, bst_minor,
                                  self.base_type.__name__, kind,
                                  plugin_type.BST_REQUIRED_VERSION_MAJOR,
                                  plugin_type.BST_REQUIRED_VERSION_MINOR))
