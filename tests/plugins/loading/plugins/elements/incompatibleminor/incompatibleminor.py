from buildstream import Element


class IncompatibleMinor(Element):

    BST_MIN_VERSION = "2.1000"


def setup():
    return IncompatibleMinor
