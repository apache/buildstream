#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
#  Authors:
#        Tristan Maat <tristan.maat@codethink.co.uk>

import os
import platform

import psutil

from .._exceptions import PlatformError, SandboxError
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
        from ..sandbox._sandboxbuildboxrun import SandboxBuildBoxRun  # pylint: disable=cyclic-import

        # Try to setup buildbox-run sandbox, otherwise fallback to the dummy sandbox.
        try:
            self._check_sandbox(SandboxBuildBoxRun)
        except (SandboxError, utils.ProgramNotFoundError):
            pass

    def _check_sandbox(self, Sandbox):
        Sandbox._dummy_reasons = []
        try:
            Sandbox.check_available()
        except SandboxError as Error:
            self.dummy_reasons += Sandbox._dummy_reasons
            raise Error

    @classmethod
    def create_instance(cls) -> "Platform":
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
            "riscv32": "rv32g",
            "riscv64": "rv64g",
            "rv32g": "rv32g",
            "rv64g": "rv64g",
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
        from ..sandbox._sandboxbuildboxrun import SandboxBuildBoxRun  # pylint: disable=cyclic-import

        if self.dummy_reasons:
            dummy_reasons = " and ".join(self.dummy_reasons)
        else:
            try:
                SandboxBuildBoxRun.check_sandbox_config(kwargs["config"])
                return SandboxBuildBoxRun(*args, **kwargs)
            except SandboxError as e:
                dummy_reasons = str(e)

        kwargs["dummy_reason"] = dummy_reasons
        return SandboxDummy(*args, **kwargs)
