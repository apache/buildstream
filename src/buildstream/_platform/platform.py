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

import multiprocessing
import os
import platform
import sys

import psutil

from .._exceptions import PlatformError, ImplError, SandboxError
from .. import utils


class Platform:
    # Platform()
    #
    # A class to manage platform-specific details. Currently holds the
    # sandbox factory as well as platform helpers.
    #
    # Args:
    #     force_sandbox (bool): Force bst to use a particular sandbox
    #
    def __init__(self, force_sandbox=None):
        self.maximize_open_file_limit()
        self._local_sandbox = None
        self.dummy_reasons = []
        self._setup_sandbox(force_sandbox)

    def _setup_sandbox(self, force_sandbox):
        # The buildbox-run interface is not platform-specific
        sandbox_setups = {"buildbox-run": self.setup_buildboxrun_sandbox, "dummy": self._setup_dummy_sandbox}

        preferred_sandboxes = [
            "buildbox-run",
        ]

        self._try_sandboxes(force_sandbox, sandbox_setups, preferred_sandboxes)

    def _try_sandboxes(self, force_sandbox, sandbox_setups, preferred_sandboxes):
        # Any sandbox from sandbox_setups can be forced by BST_FORCE_SANDBOX
        # But if a specific sandbox is not forced then only `first class` sandbox are tried before
        # falling back to the dummy sandbox.
        # Where `first_class` sandboxes are those in preferred_sandboxes
        if force_sandbox:
            try:
                sandbox_setups[force_sandbox]()
            except KeyError:
                raise PlatformError(
                    "Forced Sandbox is unavailable on this platform: BST_FORCE_SANDBOX"
                    " is set to {} but it is not available".format(force_sandbox)
                )
            except SandboxError as Error:
                raise PlatformError(
                    "Forced Sandbox Error: BST_FORCE_SANDBOX"
                    " is set to {} but cannot be setup".format(force_sandbox),
                    detail=" and ".join(self.dummy_reasons),
                ) from Error
        else:
            for good_sandbox in preferred_sandboxes:
                try:
                    sandbox_setups[good_sandbox]()
                    return
                except SandboxError:
                    continue
                except utils.ProgramNotFoundError:
                    continue
            sandbox_setups["dummy"]()

    def _check_sandbox(self, Sandbox):
        Sandbox._dummy_reasons = []
        try:
            Sandbox.check_available()
        except SandboxError as Error:
            self.dummy_reasons += Sandbox._dummy_reasons
            raise Error

    @classmethod
    def create_instance(cls):
        # Meant for testing purposes and therefore hidden in the
        # deepest corners of the source code. Try not to abuse this,
        # please?
        if os.getenv("BST_FORCE_SANDBOX"):
            force_sandbox = os.getenv("BST_FORCE_SANDBOX")
        else:
            force_sandbox = None

        if os.getenv("BST_FORCE_BACKEND"):
            backend = os.getenv("BST_FORCE_BACKEND")
        elif sys.platform.startswith("darwin"):
            backend = "darwin"
        elif sys.platform.startswith("linux"):
            backend = "linux"
        elif sys.platform == "win32":
            backend = "win32"
        else:
            backend = "fallback"

        if backend == "linux":
            from .linux import Linux as PlatformImpl  # pylint: disable=cyclic-import
        elif backend == "darwin":
            from .darwin import Darwin as PlatformImpl  # pylint: disable=cyclic-import
        elif backend == "win32":
            from .win32 import Win32 as PlatformImpl  # pylint: disable=cyclic-import
        elif backend == "fallback":
            from .fallback import Fallback as PlatformImpl  # pylint: disable=cyclic-import
        else:
            raise PlatformError("No such platform: '{}'".format(backend))

        return PlatformImpl(force_sandbox=force_sandbox)

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

    # does_multiprocessing_start_require_pickling():
    #
    # Returns True if the multiprocessing start method will pickle arguments
    # to new processes.
    #
    # Returns:
    #    (bool): Whether pickling is required or not
    #
    def does_multiprocessing_start_require_pickling(self):
        # Note that if the start method has not been set before now, it will be
        # set to the platform default by `get_start_method`.
        return multiprocessing.get_start_method() != "fork"

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

    def maximize_open_file_limit(self):
        # Need to set resources for _frontend/app.py as this is dependent on the platform
        # SafeHardlinks FUSE needs to hold file descriptors for all processes in the sandbox.
        # Avoid hitting the limit too quickly, by increasing it as far as we can.

        # Import this late, as it is not available on Windows. Note that we
        # could use `psutil.Process().rlimit` instead, but this would introduce
        # a dependency on the `prlimit(2)` call, which seems to only be
        # available on Linux. For more info:
        # https://github.com/giampaolo/psutil/blob/cbf2bafbd33ad21ef63400d94cb313c299e78a45/psutil/_psutil_linux.c#L45
        import resource

        soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
        if soft_limit != hard_limit:
            resource.setrlimit(resource.RLIMIT_NOFILE, (hard_limit, hard_limit))

    def _setup_dummy_sandbox(self):
        raise ImplError(
            "Platform {platform} does not implement _setup_dummy_sandbox()".format(platform=type(self).__name__)
        )

    # Buildbox run sandbox methods
    def _check_sandbox_config_buildboxrun(self, config):
        from ..sandbox._sandboxbuildboxrun import SandboxBuildBoxRun  # pylint: disable=cyclic-import

        SandboxBuildBoxRun.check_sandbox_config(self, config)

    @staticmethod
    def _create_buildboxrun_sandbox(*args, **kwargs):
        from ..sandbox._sandboxbuildboxrun import SandboxBuildBoxRun  # pylint: disable=cyclic-import

        return SandboxBuildBoxRun(*args, **kwargs)

    def setup_buildboxrun_sandbox(self):
        from ..sandbox._sandboxbuildboxrun import SandboxBuildBoxRun  # pylint: disable=cyclic-import

        self._check_sandbox(SandboxBuildBoxRun)
        self.check_sandbox_config = self._check_sandbox_config_buildboxrun
        self.create_sandbox = self._create_buildboxrun_sandbox
        return True
