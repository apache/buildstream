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
import sys
import resource

import psutil

from .._exceptions import PlatformError, ImplError


class Platform():
    _instance = None

    # Platform()
    #
    # A class to manage platform-specific details. Currently holds the
    # sandbox factory as well as platform helpers.
    #
    def __init__(self):
        self.set_resource_limits()

    @classmethod
    def _create_instance(cls):
        # Meant for testing purposes and therefore hidden in the
        # deepest corners of the source code. Try not to abuse this,
        # please?
        if os.getenv('BST_FORCE_BACKEND'):
            backend = os.getenv('BST_FORCE_BACKEND')
        elif sys.platform.startswith('linux'):
            backend = 'linux'
        elif sys.platform.startswith('darwin'):
            backend = 'darwin'
        else:
            backend = 'unix'

        if backend == 'linux':
            from .linux import Linux as PlatformImpl  # pylint: disable=cyclic-import
        elif backend == 'darwin':
            from .darwin import Darwin as PlatformImpl  # pylint: disable=cyclic-import
        elif backend == 'unix':
            from .unix import Unix as PlatformImpl  # pylint: disable=cyclic-import
        else:
            raise PlatformError("No such platform: '{}'".format(backend))

        cls._instance = PlatformImpl()

    @classmethod
    def get_platform(cls):
        if not cls._instance:
            cls._create_instance()
        return cls._instance

    def get_cpu_count(self, cap=None):
        cpu_count = len(psutil.Process().cpu_affinity())
        if cap is None:
            return cpu_count
        else:
            return min(cpu_count, cap)

    @staticmethod
    def get_host_os():
        return platform.uname().system

    # canonicalize_arch():
    #
    # This returns the canonical, OS-independent architecture name
    # or raises a PlatformError if the architecture is unknown.
    #
    @staticmethod
    def canonicalize_arch(arch):
        # Note that these are all expected to be lowercase, as we want a
        # case-insensitive lookup. Windows can report its arch in ALLCAPS.
        aliases = {
            "aarch32": "aarch32",
            "aarch64": "aarch64",
            "aarch64-be": "aarch64-be",
            "amd64": "x86-64",
            "arm": "aarch32",
            "armv8l": "aarch64",
            "armv8b": "aarch64-be",
            "i386": "x86-32",
            "i486": "x86-32",
            "i586": "x86-32",
            "i686": "x86-32",
            "power-isa-be": "power-isa-be",
            "power-isa-le": "power-isa-le",
            "ppc64": "power-isa-be",
            "ppc64le": "power-isa-le",
            "sparc": "sparc-v9",
            "sparc64": "sparc-v9",
            "sparc-v9": "sparc-v9",
            "x86-32": "x86-32",
            "x86-64": "x86-64"
        }

        try:
            return aliases[arch.replace('_', '-').lower()]
        except KeyError:
            raise PlatformError("Unknown architecture: {}".format(arch))

    # get_host_arch():
    #
    # This returns the architecture of the host machine. The possible values
    # map from uname -m in order to be a OS independent list.
    #
    # Returns:
    #    (string): String representing the architecture
    @staticmethod
    def get_host_arch():
        # get the hardware identifier from uname
        uname_machine = platform.uname().machine
        return Platform.canonicalize_arch(uname_machine)

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

    def check_sandbox_config(self, config):
        raise ImplError("Platform {platform} does not implement check_sandbox_config()"
                        .format(platform=type(self).__name__))

    def set_resource_limits(self, soft_limit=None, hard_limit=None):
        # Need to set resources for _frontend/app.py as this is dependent on the platform
        # SafeHardlinks FUSE needs to hold file descriptors for all processes in the sandbox.
        # Avoid hitting the limit too quickly.
        limits = resource.getrlimit(resource.RLIMIT_NOFILE)
        if limits[0] != limits[1]:
            if soft_limit is None:
                soft_limit = limits[1]
            if hard_limit is None:
                hard_limit = limits[1]
            resource.setrlimit(resource.RLIMIT_NOFILE, (soft_limit, hard_limit))
