from buildstream import Source


class FooSource(Source):

    # We have a little while until we have to manually modify this
    BST_REQUIRED_VERSION_MAJOR = 5000


def setup():
    return FooSource
