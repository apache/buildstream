from buildstream import Element
from buildstream.plugin import CoreWarnings


class CoreWarn(Element):

    BST_MIN_VERSION = "2.0"

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
        self.warn("Testing: CoreWarning produced during assemble", warning_token=CoreWarnings.OVERLAPS)


def setup():
    return CoreWarn
