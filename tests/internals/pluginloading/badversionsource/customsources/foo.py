from buildstream import Source


class BarSource(Source):

    BST_FORMAT_VERSION = 5

    def preflight(self):
        pass

    def configure(self, node):
        pass


def setup():
    return BarSource
