from buildstream import Source


class FooSource(Source):

    BST_MIN_VERSION = "2.0"

    def preflight(self):
        pass

    def configure(self, node):
        pass

    def get_unique_key(self):
        pass


def setup():
    return FooSource
