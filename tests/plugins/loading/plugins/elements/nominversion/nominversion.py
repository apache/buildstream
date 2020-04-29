# Plugins are required to specify the BST_MIN_VERSION
from buildstream import Element


class NoMinVersion(Element):
    pass


def setup():
    return NoMinVersion
