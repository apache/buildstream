import os
from buildstream import Element

WARNING_A = "warning-a"


class WarningA(Element):
    def configure(self, node):
        pass

    def preflight(self):
        pass

    def get_unique_key(self):
        pass

    def configure_sandbox(self, sandbox):
        pass

    def stage(self, sandbox):
        pass

    def assemble(self, sandbox):
        self.warn("Testing: warning-a produced during assemble", warning_token=WARNING_A)

        # Return an arbitrary existing directory in the sandbox
        #
        rootdir = sandbox.get_directory()
        install_root = self.get_variable('install-root')
        outputdir = os.path.join(rootdir, install_root.lstrip(os.sep))
        os.makedirs(outputdir, exist_ok=True)
        return install_root


def setup():
    return WarningA
