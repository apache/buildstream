# Plugins are required to specify the BST_MIN_VERSION
from buildstream import Element


class MalformedMinVersion(Element):

    BST_MIN_VERSION = 2.0


def setup():
    return MalformedMinVersion
