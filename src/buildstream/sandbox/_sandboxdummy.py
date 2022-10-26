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

from .._exceptions import SandboxError
from .sandbox import Sandbox, SandboxCommandError


class SandboxDummy(Sandbox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reason = kwargs.get("dummy_reason", "no reason given")

    def _run(self, command, *, flags, cwd, env):

        if not self._has_command(command[0], env):
            raise SandboxCommandError(
                "Staged artifacts do not provide command " "'{}'".format(command[0]), reason="missing-command"
            )

        raise SandboxError(
            "This platform does not support local builds: {}".format(self._reason), reason="unavailable-local-sandbox"
        )
