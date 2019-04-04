from buildstream2 import Source


class FooSource(Source):
    pass


def setup():
    return FooSource
