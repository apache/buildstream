from buildstream import Element


class Found(Element):
    BST_MIN_VERSION = "2.0"

    def configure(self, node):
        pass

    def preflight(self):
        pass

    def get_unique_key(self):
        return {}


# Plugin entry point
def setup():
    return Found
