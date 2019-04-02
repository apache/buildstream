import os

from .._exceptions import PlatformError
from ..sandbox import SandboxNone

from . import Platform


class Win32(Platform):

    def __init__(self):

        super().__init__()

    def create_sandbox(self, *args, **kwargs):
        kwargs['dummy_reason'] = \
            "There are no supported sandbox " + \
            "technologies for Win32 at this time"
        return SandboxNone(*args, **kwargs)

    def check_sandbox_config(self, config):
        # Check host os and architecture match
        if config.build_os != self.get_host_os():
            raise PlatformError("Configured and host OS don't match.")
        elif config.build_arch != self.get_host_arch():
            raise PlatformError("Configured and host architecture don't match.")

        return True
