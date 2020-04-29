from buildstream import Element


class FooElement(Element):

    BST_MIN_VERSION = "2.0"

    def configure(self, config):
        pass

    def preflight(self):
        pass

    def get_unique_key(self):
        return "foo"


def setup():
    return FooElement
