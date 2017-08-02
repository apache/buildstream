#!/usr/bin/env python3
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
import platform

from .. import utils
from .. import PlatformError, ProgramNotFoundError, ImplError


class Platform():

    # Platform()
    #
    # A class to manage platform-specific details. Currently holds the
    # sandbox factory, the artifact cache and staging operations, as
    # well as platform helpers.
    #
    # Args:
    #     system_platform (str): A platform identifier as given by sys.platform
    #
    def __init__(self, context, system_platform):
        self.context = context
        self._platform_string = system_platform

    @classmethod
    def get_platform(cls, *args, **kwargs):

        have_bwrap = True
        have_ostree = True

        try:
            utils.get_host_tool('bwrap')
        except ProgramNotFoundError:
            have_bwrap = False

        try:
            utils.get_host_tool('ostree')
        except ProgramNotFoundError:
            have_ostree = False

        # Meant for testing purposes and therefore hidden in the
        # deepest corners of the source code. Try not to abuse this,
        # please?
        forced_backend = os.getenv('BST_FORCE_BACKEND')

        if forced_backend == 'linux' or not forced_backend and have_bwrap and have_ostree:
            from .linux import Linux as PlatformImpl
        elif forced_backend == 'unix' or not forced_backend:
            from .unix import Unix as PlatformImpl
        else:
            raise PlatformError("No such platform: '{}'".format(forced_backend))

        return PlatformImpl(*args, **kwargs)

    ##################################################################
    #                       Platform properties                      #
    ##################################################################
    @property
    def artifactcache(self):
        raise ImplError("Platform {platform} does not implement an artifactcache"
                        .format(platform=type(self).__name__))

    @property
    def platform_name(self):
        return self._platform_string

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

    ##################################################################
    #                             Staging                            #
    ##################################################################

    # stage_artifact():
    #
    # Stage an extracted artifact
    #
    # Args:
    #     artifact (str): The path to the files to stage (can things other than bst artifacts)
    #     sandbox (:class:`.Sandbox`): The build sandbox
    #     path (str): An optional sandbox relative path
    #     files (list): An optional list of files in the given path to stage
    #
    #     Returns:
    #         (:class:`~.utils.FileListResult`): The result describing what happened while staging
    #
    def stage_to_sandbox(self, artifact, sandbox, path=None, files=None):
        raise ImplError("Platform {platform} does not implement stage_to_sandbox()"
                        .format(platform=type(self).__name__))

    ##################################################################
    #                             Helpers                            #
    ##################################################################

    # switch():
    #
    # Switch between values depending on the host platform
    #
    # Keyword Args:
    #     default (Object): A value to return if no given platform
    #                       matches
    #     linux (Object): The value to return on linux
    #     sunos (Object): The value to return on sunos
    #     aix (Object): The value to return on aix
    #
    # Raises:
    #     PlatformError:
    #         If no platform matches the given parameters and no
    #         'default' value is given
    #
    # Examples:
    #     Use different mount commands on different platforms:
    #         command = platform.switch(sunos=["mount", "-F", "lofs"],
    #                                   default=["mount", "--rbind"])
    #         subprocess.call(command)
    #
    # This method *does* support other platforms, as long as the
    # python-specific platform string ``starts with'' the keyword
    # argument's name (e.g. darwin for OS X switches).
    #
    # This is just a note for documentation purposes, buildstream does
    # not currently support other platforms.
    #
    def switch(self, **kwargs):
        for plat, value in kwargs.items():
            if self._platform_string.startswith(plat):
                return value

        try:
            return kwargs['default']
        except KeyError:
            pass

        raise PlatformError('Platform {} is not supported'.format(platform.platform()))
