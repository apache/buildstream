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
import copy
import inspect

from . import _yaml
from . import ImplError


class Element():
    """Element()

    Base Element class.

    All elements derive from this class, this interface defines how
    the core will be interacting with Elements.
    """
    __defaults = {}          # The defaults from the yaml file and project
    __defaults_set = False   # Flag, in case there are no defaults at all

    def __init__(self, context, project, meta):

        self.__context = context                                    # The Context object
        self.__project = project                                    # The Project object
        self.__provenance = _yaml.node_get_provenance(meta.config)  # Provenance information

        self.name = meta.name
        """The element name"""

        self.__init_defaults()

        config = self.__extract_config(meta)
        self.configure(config)

    # Element implementations may stringify themselves for the purpose of logging and errors
    def __str__(self):
        return "%s - %s element declared in %s" % (self.name, self.get_kind(), self.__provenance.filename)

    def get_kind(self):
        """Fetches kind of this element

        Returns:
           (str): The kind of this element
        """
        modulename = type(self).__module__
        return modulename.split('.')[-1]

    def get_context(self):
        """Fetches the context

        Returns:
           (object): The :class:`.Context`
        """
        return self.__context

    def get_project(self):
        """Fetches the project

        Returns:
           (object): The :class:`.Project`
        """
        return self.__project

    def configure(self, node):
        """Configure the Element from loaded configuration data

        Args:
           node (dict): The loaded configuration dictionary

        Raises:
           :class:`.LoadError`

        Element implementors should implement this method to read configuration
        data and store it. Use of the the :func:`~buildstream.utils.node_get_member`
        convenience method will ensure that a nice :class:`.LoadError` is triggered
        whenever the YAML input configuration is faulty.
        """
        raise ImplError("Element plugin '%s' does not implement configure()" % self.get_kind())

    def preflight(self):
        """Preflight Check

        Raises:
           :class:`.ElementError`

        The method is run during pipeline preflight check, elements
        should use this method to determine if they are able to
        function in the host environment or if the data is unsuitable.

        Implementors should simply raise :class:`.ElementError` with
        an informative message in the case that the host environment is
        unsuitable for operation.
        """
        raise ImplError("Element plugin '%s' does not implement preflight()" % self.get_kind())

    def get_unique_key(self):
        """Return something which uniquely identifies the element

        Returns:
           A string, list or dictionary which uniquely identifies the element to use
        """
        raise ImplError("Element plugin '%s' does not implement get_unique_key()" % self.get_kind())

    #############################################################
    #                       Private Methods                     #
    #############################################################
    def __init_defaults(self):

        # Defaults are loaded once per class and then reused
        #
        if not self.__defaults_set:

            # Get the yaml file in the same directory as the plugin
            plugin_file = inspect.getfile(type(self))
            plugin_dir = os.path.dirname(plugin_file)
            plugin_conf_name = "%s.yaml" % self.get_kind()
            plugin_conf = os.path.join(plugin_dir, "%s.yaml" % self.get_kind())

            # Override some plugin defaults with project overrides
            #
            defaults = {}
            elements = self.__project._elements
            overrides = elements.get(self.get_kind)
            try:
                defaults = _yaml.load(plugin_conf, plugin_conf_name)
                if overrides:
                    _yaml.composite(defaults, overrides, typesafe=True)
            except LoadError as e:
                # Ignore missing file errors, element's may omit a config file.
                if e.reason == LoadErrorReason.MISSING_FILE:
                    if overrides:
                        defaults = copy.deepcopy(overrides)
                else:
                    raise e

            # Set the data class wide
            type(self).__defaults = defaults
            self.__defaults_set = True

    # This will resolve the final configuration to be handed
    # off to element.configure()
    #
    def __extract_config(self, meta):
        default_config = _yaml.node_get(self.__defaults, dict, 'config', default_value={})
        config = meta.config

        if not config:
            config = default_config
        elif default_config:
            _yaml.composite(default_config, config, typesafe=True)
            config = default_config

        if not config:
            config = {}

        return config
