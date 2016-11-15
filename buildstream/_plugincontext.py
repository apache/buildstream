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

        # Raise an error if we have more than one plugin with the same name
        self.assert_searchpath(searchpath)

        self.source = base.make_plugin_source(searchpath=searchpath)
        for kind in self.source.list_plugins():
            self.load_plugin(kind)

    def load_plugin(self, kind):

        plugin = self.source.load_plugin(kind)
        try:
            plugin_type = plugin.setup()
        except AttributeError as e:
            raise PluginError ("%s plugin '%s' did not provide a setup() function" %
                               (self.base_type.__name__, kind)) from e
        except TypeError as e:
            raise PluginError ("setup symbol in %s plugin '%s' is not a function" %
                               (self.base_type.__name__, kind)) from e

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
                raise PluginError ("%s plugin '%s' returned type '%s', which is not a subclass of %s" %
                                   (self.base_type.__name__, kind, plugin_type.__name__, self.base_type.__name__))
        except TypeError as e:
            raise PluginError ("%s plugin '%s' returned something that is not an %s subclass" %
                               (self.base_type.__name__, kind, self.base_type.__name__)) from e

    # We want a PluginError when trying to create a context
    # where more than one plugin has the same name
    def assert_searchpath(self, searchpath):
        names=[]
        fullnames=[]
        for path in searchpath:
            for filename in os.listdir(path):
                basename = os.path.basename(filename)
                name, extension = os.path.splitext(basename)
                if extension == '.py' and name != '__init__':
                    fullname = os.path.join (path, filename)

                    if name in names:
                        idx = names.index(name)
                        raise PluginError (
                            "Failed to register %s plugin '%s' from: %s\n"
                            "%s plugin '%s' is already registered by: %s" %
                            (self.base_type.__name__, name, fullname,
                             self.base_type.__name__, name, fullnames[idx]))

                    names.append(name)
                    fullnames.append(fullname)
