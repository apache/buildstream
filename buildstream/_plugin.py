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

from .exceptions import PluginError

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
class _PluginContext():

    def __init__(self, plugin_base, base_type, searchpath=None):

        if not searchpath:
            raise PluginError ("Cannot create plugin context without any searchpath")

        self.base_type = base_type; # The expected base class which plugins are to derive from
        self.source    = None       # The PluginSource object
        self.types     = {}         # Dictionary to lookup plugin types by their kind

        self.load_plugins(plugin_base, searchpath)

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
        if not kind in self.types:
            raise PluginError ("No %s type registered for kind '%s'" %
                               (self.base_type.__name__, kind))

        return self.types[kind]

    def load_plugins(self, base, searchpath):
        self.source = base.make_plugin_source(searchpath=searchpath)
        for kind in self.source.list_plugins():
            self.load_plugin(kind)

    def load_plugin(self, kind):

        plugin      = self.source.load_plugin(kind)
        plugin_type = plugin.setup()

        self.assert_plugin (kind, plugin_type)

        print ("Registering %s plugin %s for kind %s" %
               (self.base_type.__name__, plugin_type.__name__, kind))
        self.types[kind] = plugin_type

    def assert_plugin(self, kind, plugin_type):
        if kind in self.types:
            raise PluginError ("Tried to register %s plugin for existing kind '%s' (already registered %s)" %
                               (self.base_type.__name__, kind, self.types[kind].__name__))
        try:
            if not issubclass(plugin_type, self.base_type):
                raise PluginError ("%s plugin '%s' returned type '%s', which is not a subclass of Plugin" %
                                   (self.base_type.__name__, kind, plugin_type.__name__))
        except TypeError as e:
            raise PluginError ("%s plugin '%s' returned something that is not an Plugin subclass" %
                               (self.base_type.__name__, kind)) from e
