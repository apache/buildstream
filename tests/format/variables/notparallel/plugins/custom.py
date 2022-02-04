from buildstream import BuildElement


# A custom build element
class CustomElement(BuildElement):

    BST_MIN_VERSION = "2.0"


# Plugin entry point
def setup():
    return CustomElement
