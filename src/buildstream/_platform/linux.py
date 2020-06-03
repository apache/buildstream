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

from ..sandbox import SandboxDummy

from .platform import Platform


class Linux(Platform):

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
