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
#        Andrew Leeming <andrew.leeming@codethink.co.uk>
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
"""Sandbox abstraction layer.

:class:`.Element` plugins which want to interface with the sandbox
need only understand this interface, while it may be given a different
sandbox implementation, any sandbox implementation it is given will
conform to this interface.
"""
from . import ImplError


class SandboxFlags():
    ROOT_READ_ONLY = 0x01
    """The root filesystem is read only.

    This is normally true except when running integration commands
    on staged dependencies, where we have to update caches and run
    things such as ldconfig.
    """

    NETWORK_ENABLED = 0x02
    """Whether to expose host network.

    This should not be set when running builds, but can
    be allowed for running a shell in a sandbox.
    """


class Sandbox():
    """Sandbox()

    Sandbox programming interface for :class:`.Element` plugins.
    """
    def __init__(self, context, project, directory, stdout=None, stderr=None):
        self.__context = context
        self.__project = project
        self.__directory = directory
        self.__stdout = stdout
        self.__stderr = stderr

    def run(self, command, flags, cwd=None, env=None):
        """Run a command in the sandbox.

        Args:
            command (list): The command to run in the sandboxed environment, as a list
                            of strings starting with the binary to run.
            flags (:class:`.SandboxFlags`): The flags for running this command.
            cwd (str): The sandbox relative working directory in which to run the command.
            env (dict): A dictionary of string key, value pairs to set as environment
                        variables inside the sandbox environment.

        Returns:
            (int): The program exit code.

        Raises:
            (:class:`.ProgramNotFoundError`): If a host tool which the given sandbox
                                              implementation requires is not found.
        """
        raise ImplError("Sandbox of type '{}' does not implement run()"
                        .format(type(self).__name__))

    def get_directory(self):
        """Fetches the directory of this sandbox

        Returns:
           (str): The sandbox root directory
        """
        return self.__directory

    ################################################
    #               Private methods                #
    ################################################
    # _get_context()
    #
    # Fetches the context BuildStream was launched with.
    #
    # Returns:
    #    (Context): The context of this BuildStream invocation
    def _get_context(self):
        return self.__context

    # _get_project()
    #
    # Fetches the Project this sandbox was created to build for.
    #
    # Returns:
    #    (Project): The project this sandbox was created for.
    def _get_project(self):
        return self.__project

    # _get_output()
    #
    # Fetches the stdout & stderr
    #
    # Returns:
    #    (file): The stdout, or None to inherit
    #    (file): The stderr, or None to inherit
    def _get_output(self):
        return (self.__stdout, self.__stderr)
