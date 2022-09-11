from .._exceptions import SandboxError
from . import Sandbox


# SandboxDummy()
#
# Dummy sandbox to use on a different.
#
class SandboxDummy(Sandbox):
    def __init__(self, reason, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reason = reason

    def run(self, command, flags, *, cwd=None, env=None):
        raise SandboxError(self._reason)
