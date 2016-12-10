from buildstream import Source


class AnotherFooSource(Source):
    pass


def setup():
    return AnotherFooSource
