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
  .. literalinclude:: ../../buildstream/data/userconfig.yaml
     :language: yaml
"""

import os
import hashlib
import pickle
from . import _site
from . import _yaml
from . import utils
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

        # Private variables
        self._cache_key = None
        self._message_handler = None

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
        defaults = _yaml.load(_site.default_user_config)
        if config:
            user_config = _yaml.load(config)
            _yaml.composite(defaults, user_config, typesafe=True)

        for dir in ['sourcedir', 'builddir', 'deploydir', 'artifactdir', 'ccachedir']:
            setattr(self, dir, os.path.expanduser(_yaml.node_get(defaults, str, dir)))

    #############################################################
    #            Private Methods used in BuildStream            #
    #############################################################

    # _set_message_handler()
    #
    # Sets the handler for any status messages propagated through
    # the context.
    #
    # The message handler should have the same signature as
    # the _message() method
    def _set_message_handler(self, handler):
        self._message_handler = handler

    # _get_cache_key():
    #
    # Returns the cache key, calculating it if necessary
    #
    # Returns:
    #    (str): A hex digest cache key for the Context
    #
    def _get_cache_key(self):
        if self._cache_key is None:

            # Anything that alters the build goes into the unique key
            self.__cache_key = utils._generate_key({
                'arch': self.arch
            })

        return self.__cache_key

    # _message():
    #
    # Proxies a message back to the caller
    #
    # Args:
    #    message: A _Message object (from plugin.py)
    #
    def _message(self, message):
        # Send it off to the frontend
        if self._message_handler is not None:
            self._message_handler(message)
            return

        # Dummy default implementation
        fmt = "{type}: {message}"
        if message.detail is not None:
            fmt += "\n\n{detail}\n"

        message = fmt.format(type=message.message_type,
                             message=message.message,
                             detail=message.detail)
        print(message)
