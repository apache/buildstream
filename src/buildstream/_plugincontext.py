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

from ._exceptions import PluginError, LoadError
from .exceptions import LoadErrorReason
from . import utils


# A Context for loading plugin types
#
# Args:
#     plugin_base (PluginBase): The main PluginBase object to work with
#     base_type (type):         A base object type for this context
#     site_plugin_path (str):   Path to where buildstream keeps plugins
#     entrypoint_group (str):   Name of the entry point group that provides plugins
#     plugin_origins (list):    Data used to search for plugins
#     format_versions (dict):   A dict of meta.kind to the integer minimum
#                               version number for each plugin to be loaded
#
# Since multiple pipelines can be processed recursively
# within the same interpretor, it's important that we have
# one context associated to the processing of a given pipeline,
# this way sources and element types which are particular to
# a given BuildStream project are isolated to their respective
# Pipelines.
#
class PluginContext:
    def __init__(
        self, plugin_base, base_type, site_plugin_path, entrypoint_group, *, plugin_origins=None, format_versions={}
    ):

        # For pickling across processes, make sure this context has a unique
        # identifier, which we prepend to the identifier of each PluginSource.
        # This keeps plugins loaded during the first and second pass distinct
        # from eachother.
        self._identifier = str(id(self))

        # The plugin kinds which were loaded
        self.loaded_dependencies = []

        #
        # Private members
        #
        self._base_type = base_type  # The base class plugins derive from
        self._types = {}  # Plugin type lookup table by kind
        self._plugin_origins = plugin_origins or []

        # The PluginSource object
        self._plugin_base = plugin_base
        self._site_plugin_path = site_plugin_path
        self._entrypoint_group = entrypoint_group
        self._alternate_sources = {}
        self._format_versions = format_versions

        self._init_site_source()

    def _init_site_source(self):
        self._site_source = self._plugin_base.make_plugin_source(
            searchpath=self._site_plugin_path, identifier=self._identifier + "site",
        )

    def __getstate__(self):
        state = self.__dict__.copy()

        # PluginSource is not a picklable type, so we must reconstruct this one
        # as best we can when unpickling.
        #
        # Since the values of `_types` depend on the PluginSource, we must also
        # get rid of those. It is only a cache - we will automatically recreate
        # them on demand.
        #
        # Similarly we must clear out the `_alternate_sources` cache.
        #
        # Note that this method of referring to members is error-prone in that
        # a later 'search and replace' renaming might miss these. Guard against
        # this by making sure we are not creating new members, only clearing
        # existing ones.
        #
        del state["_site_source"]
        assert "_types" in state
        state["_types"] = {}
        assert "_alternate_sources" in state
        state["_alternate_sources"] = {}

        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

        # Note that in order to enable plugins to be unpickled along with this
        # PluginSource, we would also have to set and restore the 'identifier'
        # of the PluginSource. We would also have to recreate `_types` as it
        # was before unpickling them. We are not using this method in
        # BuildStream, so the identifier is not restored here.
        self._init_site_source()

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
        return self._ensure_plugin(kind)

    # all_loaded_plugins():
    #
    # Returns: an iterable over all the loaded plugins.
    #
    def all_loaded_plugins(self):
        return self._types.values()

    def _get_local_plugin_source(self, path):
        if ("local", path) not in self._alternate_sources:
            # key by a tuple to avoid collision
            source = self._plugin_base.make_plugin_source(searchpath=[path], identifier=self._identifier + path,)
            # Ensure that sources never get garbage collected,
            # as they'll take the plugins with them.
            self._alternate_sources[("local", path)] = source
        else:
            source = self._alternate_sources[("local", path)]
        return source

    def _get_pip_plugin_source(self, package_name, kind):
        defaults = None
        if ("pip", package_name) not in self._alternate_sources:
            import pkg_resources

            # key by a tuple to avoid collision
            try:
                package = pkg_resources.get_entry_info(package_name, self._entrypoint_group, kind)
            except pkg_resources.DistributionNotFound as e:
                raise PluginError("Failed to load {} plugin '{}': {}".format(self._base_type.__name__, kind, e)) from e

            if package is None:
                raise PluginError("Pip package {} does not contain a plugin named '{}'".format(package_name, kind))

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

            source = self._plugin_base.make_plugin_source(
                searchpath=[os.path.dirname(location)], identifier=self._identifier + os.path.dirname(location),
            )
            self._alternate_sources[("pip", package_name)] = source

        else:
            source = self._alternate_sources[("pip", package_name)]

        return source, defaults

    def _ensure_plugin(self, kind):

        if kind not in self._types:
            # Check whether the plugin is specified in plugins
            source = None
            defaults = None
            loaded_dependency = False

            for origin in self._plugin_origins:
                if kind not in origin.get_str_list("plugins"):
                    continue

                if origin.get_str("origin") == "local":
                    local_path = origin.get_str("path")
                    source = self._get_local_plugin_source(local_path)
                elif origin.get_str("origin") == "pip":
                    package_name = origin.get_str("package-name")
                    source, defaults = self._get_pip_plugin_source(package_name, kind)
                else:
                    raise PluginError(
                        "Failed to load plugin '{}': "
                        "Unexpected plugin origin '{}'".format(kind, origin.get_str("origin"))
                    )
                loaded_dependency = True
                break

            # Fall back to getting the source from site
            if not source:
                if kind not in self._site_source.list_plugins():
                    raise PluginError("No {} type registered for kind '{}'".format(self._base_type.__name__, kind))

                source = self._site_source

            self._types[kind] = self._load_plugin(source, kind, defaults)
            if loaded_dependency:
                self.loaded_dependencies.append(kind)

        return self._types[kind]

    def _load_plugin(self, source, kind, defaults):

        try:
            plugin = source.load_plugin(kind)

            if not defaults:
                plugin_file = inspect.getfile(plugin)
                plugin_dir = os.path.dirname(plugin_file)
                plugin_conf_name = "{}.yaml".format(kind)
                defaults = os.path.join(plugin_dir, plugin_conf_name)

        except ImportError as e:
            raise PluginError("Failed to load {} plugin '{}': {}".format(self._base_type.__name__, kind, e)) from e

        try:
            plugin_type = plugin.setup()
        except AttributeError as e:
            raise PluginError(
                "{} plugin '{}' did not provide a setup() function".format(self._base_type.__name__, kind)
            ) from e
        except TypeError as e:
            raise PluginError(
                "setup symbol in {} plugin '{}' is not a function".format(self._base_type.__name__, kind)
            ) from e

        self._assert_plugin(kind, plugin_type)
        self._assert_version(kind, plugin_type)
        return (plugin_type, defaults)

    def _assert_plugin(self, kind, plugin_type):
        if kind in self._types:
            raise PluginError(
                "Tried to register {} plugin for existing kind '{}' "
                "(already registered {})".format(self._base_type.__name__, kind, self._types[kind].__name__)
            )
        try:
            if not issubclass(plugin_type, self._base_type):
                raise PluginError(
                    "{} plugin '{}' returned type '{}', which is not a subclass of {}".format(
                        self._base_type.__name__, kind, plugin_type.__name__, self._base_type.__name__
                    )
                )
        except TypeError as e:
            raise PluginError(
                "{} plugin '{}' returned something that is not a type (expected subclass of {})".format(
                    self._base_type.__name__, kind, self._base_type.__name__
                )
            ) from e

    def _assert_version(self, kind, plugin_type):

        # Now assert BuildStream version
        bst_major, bst_minor = utils.get_bst_version()

        req_major = plugin_type.BST_REQUIRED_VERSION_MAJOR
        req_minor = plugin_type.BST_REQUIRED_VERSION_MINOR

        if (bst_major, bst_minor) < (req_major, req_minor):
            raise PluginError(
                "BuildStream {}.{} is too old for {} plugin '{}' (requires {}.{})".format(
                    bst_major,
                    bst_minor,
                    self._base_type.__name__,
                    kind,
                    plugin_type.BST_REQUIRED_VERSION_MAJOR,
                    plugin_type.BST_REQUIRED_VERSION_MINOR,
                )
            )

    # _assert_plugin_format()
    #
    # Helper to raise a PluginError if the loaded plugin is of a lesser version then
    # the required version for this plugin
    #
    def _assert_plugin_format(self, plugin, version):
        if plugin.BST_FORMAT_VERSION < version:
            raise LoadError(
                "{}: Format version {} is too old for requested version {}".format(
                    plugin, plugin.BST_FORMAT_VERSION, version
                ),
                LoadErrorReason.UNSUPPORTED_PLUGIN,
            )
