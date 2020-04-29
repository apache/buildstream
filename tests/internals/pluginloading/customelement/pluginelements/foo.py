from buildstream import Element


class FooElement(Element):

    BST_MIN_VERSION = "2.0"

    def preflight(self):
        pass

    def configure(self, node):
        pass

    def get_unique_key(self):
        return {}


def setup():
    return FooElement
