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

"""Context for running BuildStream pipelines

The :class:`.Context` object holds all of the user preferences
and context for a given invocation of BuildStream.

This is a collection of data from configuration files and command
line arguments and consists of information such as where to store
logs and artifacts, where to perform builds and cache downloaded sources,
verbosity levels and basically anything pertaining to the context
in which BuildStream was invoked.

Users can provide a configuration file to override parameters in
the default configuration.

The default BuildStream configuration is included here for reference:
  .. literalinclude:: ../../buildstream/data/defaultconfig.yaml
"""

from . import _site
from . import _yaml
from ._yaml import CompositeTypeError
from . import LoadError, LoadErrorReason


class Context():
    """Context of how BuildStream was invoked

    Args:
       arch (string): The target architecture to build for
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
        defaults = _yaml.load(_site.default_config)
        if config:
            user_config = _yaml.load(config)
            try:
                _yaml.composite_dict(defaults, user_config, typesafe=True)
            except CompositeTypeError as e:
                raise LoadError(LoadErrorReason.ILLEGAL_COMPOSITE,
                                "Expected '%s' type for configuration '%s', instead received '%s'" %
                                (e.expected_type.__name__,
                                 e.path,
                                 e.actual_type.__name__)) from e

        # Should have a loop here, but we suck
        #
        self.sourcedir = _yaml.node_get(defaults, str, 'sourcedir')
        self.builddir = _yaml.node_get(defaults, str, 'builddir')
        self.deploydir = _yaml.node_get(defaults, str, 'deploydir')
        self.artifactdir = _yaml.node_get(defaults, str, 'artifactdir')
        self.ccachedir = _yaml.node_get(defaults, str, 'ccachedir')
