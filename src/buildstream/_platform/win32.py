#
#  Copyright (C) 2019 Bloomberg Finance LP
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

from ..sandbox import SandboxDummy

from .platform import Platform


class Win32(Platform):
    @staticmethod
    def _check_dummy_sandbox_config(config):
        pass

    @staticmethod
    def _create_dummy_sandbox(*args, **kwargs):
        kwargs["dummy_reason"] = "There are no supported sandbox technologies for Win32 at this time."
        return SandboxDummy(*args, **kwargs)

    def _setup_dummy_sandbox(self):
        self.check_sandbox_config = Win32._check_dummy_sandbox_config
        self.create_sandbox = Win32._create_dummy_sandbox
        return True
