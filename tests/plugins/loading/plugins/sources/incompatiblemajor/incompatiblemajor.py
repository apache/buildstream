from buildstream import Source


class IncompatibleMajor(Source):

    BST_MIN_VERSION = "1.0"


def setup():
    return IncompatibleMajor
