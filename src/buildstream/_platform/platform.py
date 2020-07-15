#
#  Copyright (C) 2017 Codethink Limited
#  Copyright (C) 2018 Bloomberg Finance LP
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

import psutil

from .._exceptions import PlatformError, ImplError, SandboxError
from ..sandbox import SandboxDummy
from .. import utils


class Platform:
    # Platform()
    #
    # A class to manage platform-specific details. Currently holds the
    # sandbox factory as well as platform helpers.
    #
    def __init__(self):
        self._local_sandbox = None
        self.dummy_reasons = []
        self._setup_sandbox()

    def _setup_sandbox(self):
        # Try to setup buildbox-run sandbox, otherwise fallback to the dummy sandbox.
        try:
            self._setup_buildboxrun_sandbox()
        except (SandboxError, utils.ProgramNotFoundError):
            self._setup_dummy_sandbox()

    def _check_sandbox(self, Sandbox):
        Sandbox._dummy_reasons = []
        try:
            Sandbox.check_available()
        except SandboxError as Error:
            self.dummy_reasons += Sandbox._dummy_reasons
            raise Error

    @classmethod
    def create_instance(cls):
        return Platform()

    def get_cpu_count(self, cap=None):
        # `psutil.Process.cpu_affinity()` is not available on all platforms.
        # So, fallback to getting the total cpu count in cases where it is not
        # available.
        dummy_process = psutil.Process()
        if hasattr(dummy_process, "cpu_affinity"):
            cpu_count = len(dummy_process.cpu_affinity())
        else:
            cpu_count = os.cpu_count()

        if cap is None:
            return cpu_count
        else:
            return min(cpu_count, cap)

    @staticmethod
    def get_host_os():
        system = platform.uname().system.lower()

        if system == "darwin" and platform.mac_ver()[0]:
            # mac_ver() returns a non-empty release string on macOS.
            return "macos"
        else:
            return system

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
            "powerpc": "power-isa-be",
            "powerpc64": "power-isa-be",  # Used in GCC/LLVM
            "powerpc64le": "power-isa-le",  # Used in GCC/LLVM
            "ppc64": "power-isa-be",
            "ppc64le": "power-isa-le",
            "sparc": "sparc-v9",
            "sparc64": "sparc-v9",
            "sparc-v9": "sparc-v9",
            "sun4v": "sparc-v9",
            "x86-32": "x86-32",
            "x86-64": "x86-64",
        }

        try:
            return aliases[arch.replace("_", "-").lower()]
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
        uname = platform.uname()

        if uname.system.lower() == "aix":
            # IBM AIX systems reports their serial number as the machine
            # hardware identifier. So, we need to look at the reported processor
            # in this case.
            return Platform.canonicalize_arch(uname.processor)
        else:
            # Otherwise, use the hardware identifier from uname
            return Platform.canonicalize_arch(uname.machine)

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
    def create_sandbox(self, *args, **kwargs):  # pylint: disable=method-hidden
        raise ImplError("Platform {platform} does not implement create_sandbox()".format(platform=type(self).__name__))

    def check_sandbox_config(self, config):  # pylint: disable=method-hidden
        raise ImplError(
            "Platform {platform} does not implement check_sandbox_config()".format(platform=type(self).__name__)
        )

    # Buildbox run sandbox methods
    def _check_sandbox_config_buildboxrun(self, config):
        from ..sandbox._sandboxbuildboxrun import SandboxBuildBoxRun  # pylint: disable=cyclic-import

        SandboxBuildBoxRun.check_sandbox_config(self, config)

    @staticmethod
    def _create_buildboxrun_sandbox(*args, **kwargs):
        from ..sandbox._sandboxbuildboxrun import SandboxBuildBoxRun  # pylint: disable=cyclic-import

        return SandboxBuildBoxRun(*args, **kwargs)

    def _setup_buildboxrun_sandbox(self):
        from ..sandbox._sandboxbuildboxrun import SandboxBuildBoxRun  # pylint: disable=cyclic-import

        self._check_sandbox(SandboxBuildBoxRun)
        self.check_sandbox_config = self._check_sandbox_config_buildboxrun
        self.create_sandbox = self._create_buildboxrun_sandbox
        return True

    # Dummy sandbox methods
    @staticmethod
    def _check_dummy_sandbox_config(config):
        pass

    def _create_dummy_sandbox(self, *args, **kwargs):
        dummy_reasons = " and ".join(self.dummy_reasons)
        kwargs["dummy_reason"] = dummy_reasons
        return SandboxDummy(*args, **kwargs)

    def _setup_dummy_sandbox(self):
        self.check_sandbox_config = Platform._check_dummy_sandbox_config
        self.create_sandbox = self._create_dummy_sandbox
        return True
