from buildstream import Element


class IncompatibleMajor(Element):

    BST_MIN_VERSION = "1.0"


def setup():
    return IncompatibleMajor
