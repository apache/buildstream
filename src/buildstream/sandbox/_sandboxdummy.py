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

from .._exceptions import SandboxError
from .sandbox import Sandbox, SandboxCommandError


class SandboxDummy(Sandbox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reason = kwargs.get("dummy_reason", "no reason given")

    def _run(self, command, flags, *, cwd, env):

        if not self._has_command(command[0], env):
            raise SandboxCommandError(
                "Staged artifacts do not provide command " "'{}'".format(command[0]), reason="missing-command"
            )

        raise SandboxError(
            "This platform does not support local builds: {}".format(self._reason), reason="unavailable-local-sandbox"
        )
