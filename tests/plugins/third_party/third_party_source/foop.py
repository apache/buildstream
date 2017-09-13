from buildstream import Source


class FooSource(Source):
    pass


def setup():
    return FooSource
