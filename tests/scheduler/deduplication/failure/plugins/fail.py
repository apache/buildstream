from buildstream import Element, ElementError


class Fail(Element):
    BST_MIN_VERSION = "2.0"

    def configure(self, node):
        pass

    def preflight(self):
        pass

    def get_unique_key(self):
        return {}

    def configure_sandbox(self, sandbox):
        pass

    def stage(self, sandbox):
        pass

    def assemble(self, sandbox):
        raise ElementError("Failing on purpose", reason="fail")


# Plugin entry point
def setup():
    return Fail
