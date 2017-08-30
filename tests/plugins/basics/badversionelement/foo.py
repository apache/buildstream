from buildstream import Element


class FooElement(Element):

    # We have a little while until we have to manually modify this
    BST_REQUIRED_VERSION_MAJOR = 5000


def setup():
    return FooElement
