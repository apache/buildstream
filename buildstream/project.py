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

"""Loaded Project Configuration

The :class:`.Project` object holds all of the project settings from
the project configuration file including the project directory it
was loaded from.

The project configuration file should be named ``project.conf`` and
be located at the project root. It holds information such as Source
aliases relevant for the sources used in the given project as well as
overrides for the configuration of element types used in the project.

The default BuildStream project configuration is included here for reference:
  .. literalinclude:: ../../buildstream/data/projectconfig.yaml
"""

import os
from . import _site
from . import _yaml
from . import LoadError, LoadErrorReason
from .utils import node_items


# The separator we use for user specified aliases
_ALIAS_SEPARATOR = ':'


class Project():
    """Project Configuration

    Args:
       directory (string): The project directory

    Raises:
       :class:`.LoadError`
    """
    def __init__(self, directory):

        self.name = None
        """str: The project name"""

        self.directory = directory
        """str: The project directory"""

        self.environment = {}
        """dict: The base sandbox environment"""

        self.devices = []
        """list: List of device descriptions required for the sandbox"""

        self._elements = {}  # Element specific configurations
        self._aliases = {}   # Aliases dictionary

        self._load()

    def translate_url(self, url):
        """Translates the given url which may be specified with an alias
        into a fully qualified url.

        Args:
           url (str): A url, which may be using an alias

        Returns:
           str: The fully qualified url, with aliases resolved

        This method is provided for :class:`.Source` objects to resolve
        fully qualified urls based on the shorthand which is allowed
        to be specified in the YAML
        """
        if url and _ALIAS_SEPARATOR in url:
            url_alias, url_body = url.split(_ALIAS_SEPARATOR, 1)
            alias_url = self._aliases.get(url_alias)
            if alias_url:
                url = alias_url + url_body

        return url

    def _load(self):

        projectfile = os.path.join(self.directory, "project.conf")

        config = _yaml.load(_site.default_project_config)
        project_conf = _yaml.load(projectfile)
        _yaml.composite(config, project_conf, typesafe=True)

        # The project name
        self.name = _yaml.node_get(config, str, 'name')

        # Load sandbox configuration
        sandbox_node = _yaml.node_get(config, dict, 'sandbox')
        self.environment = _yaml.node_get(sandbox_node, dict, 'environment')
        self.devices = _yaml.node_get(sandbox_node, list, 'devices')

        # Aliases & Element configurations
        self._elements = _yaml.node_get(config, dict, 'elements', default_value={})
        self._aliases = _yaml.node_get(config, dict, 'aliases', default_value={})
