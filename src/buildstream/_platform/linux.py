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

from .. import utils
from ..sandbox import SandboxDummy

from .platform import Platform


class Linux(Platform):
    def _setup_sandbox(self, force_sandbox):
        sandbox_setups = {
            "bwrap": self._setup_bwrap_sandbox,
            "buildbox-run": self.setup_buildboxrun_sandbox,
            "dummy": self._setup_dummy_sandbox,
        }

        preferred_sandboxes = [
            "bwrap",
        ]

        self._try_sandboxes(force_sandbox, sandbox_setups, preferred_sandboxes)

    def __init__(self, force_sandbox=None):
        super().__init__(force_sandbox=force_sandbox)

        self._uid = os.geteuid()
        self._gid = os.getegid()

        # Set linux32 option
        self.linux32 = None

    def can_crossbuild(self, config):
        host_arch = self.get_host_arch()
        if (config.build_arch == "x86-32" and host_arch == "x86-64") or (
            config.build_arch == "aarch32" and host_arch == "aarch64"
        ):
            if self.linux32 is None:
                try:
                    utils.get_host_tool("linux32")
                    self.linux32 = True
                except utils.ProgramNotFoundError:
                    self.linux32 = False
            return self.linux32
        return False

    ################################################
    #              Private Methods                 #
    ################################################

    # Dummy sandbox methods
    @staticmethod
    def _check_dummy_sandbox_config(config):
        return True

    def _create_dummy_sandbox(self, *args, **kwargs):
        dummy_reasons = " and ".join(self.dummy_reasons)
        kwargs["dummy_reason"] = dummy_reasons
        return SandboxDummy(*args, **kwargs)

    def _setup_dummy_sandbox(self):
        self.check_sandbox_config = Linux._check_dummy_sandbox_config
        self.create_sandbox = self._create_dummy_sandbox
        return True

    # Bubble-wrap sandbox methods
    def _check_sandbox_config_bwrap(self, config):
        from ..sandbox._sandboxbwrap import SandboxBwrap

        SandboxBwrap.check_sandbox_config(self, config)

    def _create_bwrap_sandbox(self, *args, **kwargs):
        from ..sandbox._sandboxbwrap import SandboxBwrap

        kwargs["linux32"] = self.linux32
        return SandboxBwrap(*args, **kwargs)

    def _setup_bwrap_sandbox(self):
        from ..sandbox._sandboxbwrap import SandboxBwrap

        # This function should only be called once.
        # but if it does eg, in the tests we want to
        # reset the sandbox checks

        SandboxBwrap._have_good_bwrap = None
        self._check_sandbox(SandboxBwrap)
        self.check_sandbox_config = self._check_sandbox_config_bwrap
        self.create_sandbox = self._create_bwrap_sandbox
        return True
