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

from ._site import _site_info
from .utils import dictionary_override, load_yaml_dict

class Context():
    """Context of how BuildStream was invoked

    Args:
       arch (string): The target architecture to build for

    The invocation context holds state describing how BuildStream was
    invoked, this includes data such as where to store logs and artifacts,
    where to perform builds and cache downloaded sources and options
    given on the command line.
    """
    def __init__(self, arch):

        self.arch = arch
        """The target architecture to build for"""

        self.sourcedir = None
        """The directory where various sources are stored"""

        self.builddir = None
        """The directory where build sandboxes will be created"""

        self.deploydir = None
        """The directory where deployment elements will place output"""

        self.artifactdir = None
        """The local binary artifact cache directory"""

        self.ccachedir = None
        """The directory for holding ccache state"""

    def load(self, config=None):
        """Loads the configuration files

        Args:
           config (filename): The user specified configuration file, if any

        Raises:
           :class:`.LoadError`

        This will first load the BuildStream default configuration and then
        override that configuration with the configuration file indicated
        by *config*, if any was specified.
        """

        # Load default config
        #
        defaults = load_yaml_dict(_site_info['default_config'])
        if config:
            user_config = load_yaml_dict(config)
            defaults = dictionary_override(defaults, user_config)

        # Should have a loop here, but we suck
        #
        self.sourcedir = defaults.get('sourcedir')
        self.builddir = defaults.get('builddir')
        self.deploydir = defaults.get('deploydir')
        self.artifactdir = defaults.get('artifactdir')
        self.ccachedir = defaults.get('ccachedir')
