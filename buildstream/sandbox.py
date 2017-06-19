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
import os

from . import ImplError


class SandboxFlags():
    """Flags indicating how the sandbox should be run.
    """

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
        self.__stdout = stdout
        self.__stderr = stderr
        self.__directories = []
        self.__cwd = None
        self.__env = None

        # Setup the directories
        self.__directory = directory
        self.__root = os.path.join(self.__directory, 'root')
        self.__scratch = os.path.join(self.__directory, 'scratch')
        for directory in [self.__root, self.__scratch]:
            os.makedirs(directory, exist_ok=True)

    def get_directory(self):
        """Fetches the sandbox root directory

        The root directory is where artifacts for the base
        runtime environment should be staged.

        Returns:
           (str): The sandbox root directory
        """
        return self.__root

    def set_environment(self, environment):
        """Sets the environment variables for the sandbox

        Args:
           directory (dict): The environment variables to use in the sandbox
        """
        self.__env = environment

    def set_work_directory(self, directory):
        """Sets the work directory for commands run in the sandbox

        Args:
           directory (str): An absolute path within the sandbox
        """
        self.__cwd = directory

    def mark_directory(self, directory, artifact=False):
        """Marks a sandbox directory and ensures it will exist

        Args:
           directory (str): An absolute path within the sandbox to mark
           artifact (bool): Whether the content staged at this location
                            contains artifacts

        .. note::
           Any marked directories will be read-write in the sandboxed
           environment, only the root directory is allowed to be readonly.
        """
        self.__directories.append({
            'directory': directory,
            'artifact': artifact
        })

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

        .. note::

           The optional *cwd* argument will default to the value set with
           :func:`~buildstream.sandbox.Sandbox.set_work_directory`
        """
        raise ImplError("Sandbox of type '{}' does not implement run()"
                        .format(type(self).__name__))

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

    # _get_marked_directories()
    #
    # Fetches the marked directories in the sandbox
    #
    # Returns:
    #    (list): A list of directory mark objects.
    #
    # The returned objects are dictionaries with the following attributes:
    #    directory: The absolute path within the sandbox
    #    artifact: Whether the path will contain artifacts or not
    #
    def _get_marked_directories(self):
        return self.__directories

    # _get_environment()
    #
    # Fetches the environment variables for running commands
    # in the sandbox.
    #
    # Returns:
    #    (str): The sandbox work directory
    def _get_environment(self):
        return self.__env

    # _get_work_directory()
    #
    # Fetches the working directory for running commands
    # in the sandbox.
    #
    # Returns:
    #    (str): The sandbox work directory
    def _get_work_directory(self):
        return self.__cwd

    # _get_scratch_directory()
    #
    # Fetches the sandbox scratch directory, this directory can
    # be used by the sandbox implementation to cache things or
    # redirect temporary fuse mounts.
    #
    # The scratch directory is guaranteed to be on the same
    # filesystem as the root directory.
    #
    # Returns:
    #    (str): The sandbox scratch directory
    def _get_scratch_directory(self):
        return self.__scratch

    # _get_output()
    #
    # Fetches the stdout & stderr
    #
    # Returns:
    #    (file): The stdout, or None to inherit
    #    (file): The stderr, or None to inherit
    def _get_output(self):
        return (self.__stdout, self.__stderr)
