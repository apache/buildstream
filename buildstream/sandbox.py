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
#        Andrew Leeming <andrew.leeming@codethink.co.uk>

""" Sandbox abstraction layer. Allows interfacing of multiple sandbox
backends without having to know implementation details. Currently supports
bubblewrap only
"""

from enum import Enum
from ._sandboxbwrap import SandboxBwrap

Executors = Enum(value='Executors', names=['bwrap'])
"""List of the supported internal sandbox executor interfaces"""


class Sandbox:

    def __init__(self, executor=Executors.bwrap, **kwargs):
        """ Interface creation for sandboxing

        Args:
            executor (Executors): Set the executor to use internally
                This defaults to the bubblewrap implementation
        """

        self.exitcode = None
        """Cached copy of the exitcode from the last command ran"""

        self.out = None
        """Cached copy of stdout from the last command ran"""

        self.err = None
        """Cached copy of stderr from the last command ran"""

        self.executorType = executor
        """Enum string representation of the executor used internally"""

        self.executor = None
        """Object reference to actual executor being used"""

        # Set the executor based on the type provided
        if executor is Executors.bwrap:
            self.executor = SandboxBwrap(**kwargs)

    def get_executor(self):
        """Exposes the internal executor object the sandbox abstraction is using

        Returns:
            Sandbox executor object - e.g. _sandboxbwrap
        """
        return self.executor

    def set_mounts(self, mnt_list=[], global_write=False, append=False):
        """Interface for setting binds/mounts in the sandbox. `mnt_list` is
        a list of mount dicts.

        Args:
            mnt_list (list): List of dicts describing mounts.
            global_write (boolean): Set all mounts given as writable (overrides setting in dict)
            append (boolean): If set, multiple calls to `set_mounts` extends the list of mounts.
                Else they are overridden.

        The mount dict is in the format {'src','dest','type','writable'}.
            - src : Path of the mount on the HOST
            - dest : Path we wish to mount to on the TARGET
            - type : (optional) Some mounts are special such as dev, proc and tmp, and need
                to be tagged accordingly
            - writable : (optional) Boolean value to make mount writable instead of read-only

        Note: not all sandbox implementations support the full feature set. e.g. chroot
            does not allow read-only mounts, or special mounts such as dev or proc, instead
            they are treated as normal directories.
        """

        self.executor.set_mounts(mnt_list=mnt_list, global_write=global_write,
                                 append=append)

    def set_cwd(self, cwd):
        """Set the CWD for the sandbox

        Args:
            cwd (string): Path to desired working directory when the sandbox is entered
        """

        self.executor.set_cwd(cwd)

    def run(self, command):
        """Runs a command inside the sandbox environment

        Args:
            command (List[str]): The command to run in the sandboxed environment

        Raises:
            :class'`.ProgramNotfound` If the binary for an implementation can not be found

        Returns:
            exitcode, stdout, stderr
        """

        # Run command in sandbox and save outputs
        self.exitcode, self.out, self.err = self.executor.run(command)

        return self.exitcode, self.out, self.err
