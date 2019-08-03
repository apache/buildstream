import os

from buildstream import Element
from buildstream.plugin import CoreWarnings


class CoreWarn(Element):
    def configure(self, node):
        pass

    def preflight(self):
        pass

    def get_unique_key(self):
        pass

    def configure_sandbox(self, sandbox):
        sandbox.mark_directory(self.get_variable('install-root'))

    def stage(self, sandbox):
        pass

    def assemble(self, sandbox):
        self.warn("Testing: CoreWarning produced during assemble",
                  warning_token=CoreWarnings.OVERLAPS)

        # Return an arbitrary existing directory in the sandbox
        #
        rootdir = sandbox.get_directory()
        install_root = self.get_variable('install-root')
        outputdir = os.path.join(rootdir, install_root.lstrip(os.sep))
        os.makedirs(outputdir, exist_ok=True)
        return install_root


def setup():
    return CoreWarn
