from buildstream import Element

WARNING_A = "warning-a"


class WarningA(Element):

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
        self.warn("Testing: warning-a produced during assemble", warning_token=WARNING_A)


def setup():
    return WarningA
