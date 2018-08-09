from buildstream import Element

WARNING_B = "warning-b"


class WarningB(Element):
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
        self.warn("Testing: warning-b produced during assemble", warning_token=WARNING_B)


def setup():
    return WarningB
