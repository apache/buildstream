from buildstream import Source


class IncompatibleMinor(Source):

    BST_MIN_VERSION = "2.1000"


def setup():
    return IncompatibleMinor
