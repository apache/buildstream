from buildstream import Source, Consistency


class FooSource(Source):

    def preflight(self):
        pass

    def configure(self, node):
        pass

    def get_consistency(self):
        return Consistency.INCONSISTENT


def setup():
    return FooSource
