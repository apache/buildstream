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
the default configuration. Unless a configuration file is specified
on the command line when invoking ``bst``, an attempt is made to
load user specific configuration from ``$XDG_CONFIG_HOME/buildstream.conf``.

The default BuildStream configuration is included here for reference:
  .. literalinclude:: ../../buildstream/data/userconfig.yaml
     :language: yaml
"""

import os
import hashlib
import pickle
from xdg import XDG_CONFIG_HOME, XDG_CACHE_HOME, XDG_DATA_HOME
from collections import deque, Mapping
from . import _site
from . import _yaml
from . import utils
from . import LoadError, LoadErrorReason
from ._profile import Topics, profile_start, profile_end


# Force the resolved XDG variables into the environment,
# this is so that they can be used directly to specify
# preferred locations of things from user configuration
# files.
os.environ['XDG_CONFIG_HOME'] = XDG_CONFIG_HOME
os.environ['XDG_CACHE_HOME'] = XDG_CACHE_HOME
os.environ['XDG_DATA_HOME'] = XDG_DATA_HOME


class Context():
    """Context of how BuildStream was invoked

    Args:
       arch (string): The target architecture to build for
    """
    def __init__(self, arch):

        self.config_origin = None
        """Filename indicating which configuration file was used, or None for the defaults"""

        self.arch = arch
        """The target architecture to build for"""

        self.sourcedir = None
        """The directory where various sources are stored"""

        self.builddir = None
        """The directory where build sandboxes will be created"""

        self.artifactdir = None
        """The local binary artifact cache directory"""

        self.logdir = None
        """The directory to store build logs"""

        self.log_key_length = 0
        """The abbreviated cache key length to display in the UI"""

        self.log_debug = False
        """Whether debug mode is enabled"""

        self.log_verbose = False
        """Whether verbose mode is enabled"""

        self.log_error_lines = 0
        """Maximum number of lines to print from build logs"""

        self.sched_fetchers = 4
        """Maximum number of fetch or refresh tasks"""

        self.sched_builders = 4
        """Maximum number of build tasks"""

        self.sched_error_action = 'continue'
        """What to do when a build fails in non interactive mode"""

        # Private variables
        self._cache_key = None
        self._message_handler = None
        self._message_depth = deque()

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
        profile_start(Topics.LOAD_CONTEXT, 'load')

        # If a specific config file is not specified, default to trying
        # a $XDG_CONFIG_HOME/buildstream.conf file
        #
        if not config:
            default_config = os.path.join(XDG_CONFIG_HOME, 'buildstream.conf')
            if os.path.exists(default_config):
                config = default_config

        # Load default config
        #
        defaults = _yaml.load(_site.default_user_config)
        if config:
            self.config_origin = os.path.abspath(config)
            user_config = _yaml.load(config)
            _yaml.composite(defaults, user_config, typesafe=True)

        for dir in ['sourcedir', 'builddir', 'artifactdir', 'logdir']:
            # Allow the ~ tilde expansion and any environment variables in
            # path specification in the config files.
            #
            path = _yaml.node_get(defaults, str, dir)
            path = os.path.expanduser(path)
            path = os.path.expandvars(path)
            setattr(self, dir, path)

        # Load logging config
        logging = _yaml.node_get(defaults, Mapping, 'logging')
        self.log_key_length = _yaml.node_get(logging, int, 'key-length')
        self.log_debug = _yaml.node_get(logging, bool, 'debug')
        self.log_verbose = _yaml.node_get(logging, bool, 'verbose')
        self.log_error_lines = _yaml.node_get(logging, int, 'error-lines')

        # Load scheduler config
        scheduler = _yaml.node_get(defaults, Mapping, 'scheduler')
        self.sched_error_action = _yaml.node_get(scheduler, str, 'on-error')
        self.sched_fetchers = _yaml.node_get(scheduler, int, 'fetchers')
        self.sched_builders = _yaml.node_get(scheduler, int, 'builders')

        profile_end(Topics.LOAD_CONTEXT, 'load')

        valid_actions = ['continue', 'quit']
        if self.sched_error_action not in valid_actions:
            provenance = _yaml.node_get_provenance(scheduler, 'on-error')
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: on-error should be one of: {}".format(
                                provenance, ", ".join(valid_actions)))

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

    # _push_message_depth() / _pop_message_depth()
    #
    # For status messages, send the depth of timed
    # activities inside a given task through the message
    #
    def _push_message_depth(self, silent_nested):
        self._message_depth.appendleft(silent_nested)

    def _pop_message_depth(self):
        assert(self._message_depth)
        self._message_depth.popleft()

    def _silent_messages(self):
        for silent in self._message_depth:
            if silent:
                return True
        return False

    # _message():
    #
    # Proxies a message back to the caller, this is the central
    # point through which all messages pass.
    #
    # Args:
    #    message: A Message object
    #
    def _message(self, message):

        # Tag message only once
        if message.depth is None:
            message.depth = len(list(self._message_depth))

        # Send it off to the log handler (can be the frontend,
        # or it can be the child task which will log and propagate
        # to the frontend)
        assert(self._message_handler)

        self._message_handler(message, context=self)
        return
