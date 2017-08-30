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
from .exceptions import PluginError
from . import utils


# A Context for loading plugin types
#
# Args:
#     plugin_base (PluginBase): The main PluginBase object to work with
#     base_type (type):         A base object type for this context
#     searchpath (list):        A list of paths to search for plugins
#
# Since multiple pipelines can be processed recursively
# within the same interpretor, it's important that we have
# one context associated to the processing of a given pipeline,
# this way sources and element types which are particular to
# a given BuildStream project are isolated to their respective
# Pipelines.
#
class PluginContext():

    def __init__(self, plugin_base, base_type, searchpath=None):

        if not searchpath:
            raise PluginError("Cannot create plugin context without any searchpath")

        self.base_type = base_type  # The base class plugins derive from
        self.types = {}             # Plugin type lookup table by kind

        # Raise an error if we have more than one plugin with the same name
        self.assert_searchpath(searchpath)

        # The PluginSource object
        self.source = plugin_base.make_plugin_source(searchpath=searchpath)

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

    def ensure_plugin(self, kind):

        if kind not in self.types:
            if kind not in self.source.list_plugins():
                raise PluginError("No {} type registered for kind '{}'"
                                  .format(self.base_type.__name__, kind))
            self.load_plugin(kind)

        return self.types[kind]

    def load_plugin(self, kind):

        try:
            plugin = self.source.load_plugin(kind)
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
        self.types[kind] = plugin_type

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

    # We want a PluginError when trying to create a context
    # where more than one plugin has the same name
    def assert_searchpath(self, searchpath):
        names = []
        fullnames = []
        for path in searchpath:
            for filename in os.listdir(path):
                basename = os.path.basename(filename)
                name, extension = os.path.splitext(basename)
                if extension == '.py' and name != '__init__':
                    fullname = os.path.join(path, filename)

                    if name in names:
                        idx = names.index(name)
                        raise PluginError("Failed to register {} plugin '{}' from: {}\n"
                                          "{} plugin '{}' is already registered by: {}"
                                          .format(self.base_type.__name__, name, fullname,
                                                  self.base_type.__name__, name, fullnames[idx]))

                    names.append(name)
                    fullnames.append(fullname)
