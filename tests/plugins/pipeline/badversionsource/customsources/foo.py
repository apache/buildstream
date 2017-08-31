from buildstream import Source, Consistency


class BarSource(Source):

    BST_FORMAT_VERSION = 5

    def preflight(self):
        pass

    def configure(self, node):
        pass

    def get_consistency(self):
        return Consistency.INCONSISTENT


def setup():
    return BarSource
