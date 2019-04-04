from buildstream2 import Source


class AnotherFooSource(Source):
    pass


def setup():
    return AnotherFooSource
