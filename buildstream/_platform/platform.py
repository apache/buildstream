#
#  Copyright (C) 2017 Codethink Limited
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
#        Tristan Maat <tristan.maat@codethink.co.uk>

import os
import sys

from .._exceptions import PlatformError, ImplError


class Platform():
    _instance = None

    # Platform()
    #
    # A class to manage platform-specific details. Currently holds the
    # sandbox factory, the artifact cache and staging operations, as
    # well as platform helpers.
    #
    # Args:
    #     context (context): The project context
    #
    def __init__(self, context):
        self.context = context

    @classmethod
    def create_instance(cls, *args, **kwargs):
        if sys.platform.startswith('linux'):
            backend = 'linux'
        else:
            backend = 'unix'

        # Meant for testing purposes and therefore hidden in the
        # deepest corners of the source code. Try not to abuse this,
        # please?
        if os.getenv('BST_FORCE_BACKEND'):
            backend = os.getenv('BST_FORCE_BACKEND')

        if backend == 'linux':
            from .linux import Linux as PlatformImpl
        elif backend == 'unix':
            from .unix import Unix as PlatformImpl
        else:
            raise PlatformError("No such platform: '{}'".format(backend))

        cls._instance = PlatformImpl(*args, **kwargs)

    @classmethod
    def get_platform(cls):
        if not cls._instance:
            raise PlatformError("Platform needs to be initialized first")
        return cls._instance

    ##################################################################
    #                       Platform properties                      #
    ##################################################################
    @property
    def artifactcache(self):
        raise ImplError("Platform {platform} does not implement an artifactcache"
                        .format(platform=type(self).__name__))

    ##################################################################
    #                        Sandbox functions                       #
    ##################################################################

    # create_sandbox():
    #
    # Create a build sandbox suitable for the environment
    #
    # Args:
    #     args (dict): The arguments to pass to the sandbox constructor
    #     kwargs (file): The keyword arguments to pass to the sandbox constructor
    #
    # Returns:
    #     (Sandbox) A sandbox
    #
    def create_sandbox(self, *args, **kwargs):
        raise ImplError("Platform {platform} does not implement create_sandbox()"
                        .format(platform=type(self).__name__))
