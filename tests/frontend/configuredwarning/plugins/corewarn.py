from buildstream2 import Element
from buildstream2.plugin import CoreWarnings


class CoreWarn(Element):
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
        self.warn("Testing: CoreWarning produced during assemble",
                  warning_token=CoreWarnings.OVERLAPS)


def setup():
    return CoreWarn
