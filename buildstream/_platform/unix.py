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

from .._exceptions import PlatformError
from ..sandbox import SandboxChroot

from . import Platform


class Unix(Platform):

    def __init__(self):

        super().__init__()

        self._uid = os.geteuid()
        self._gid = os.getegid()

        # Not necessarily 100% reliable, but we want to fail early.
        if self._uid != 0:
            raise PlatformError("Root privileges are required to run without bubblewrap.")

    def create_sandbox(self, *args, **kwargs):
        return SandboxChroot(*args, **kwargs)

    def check_sandbox_config(self, config):
        # With the chroot sandbox, the UID/GID in the sandbox
        # will match the host UID/GID (typically 0/0).
        return config.build_uid == self._uid and config.build_gid == self._gid
