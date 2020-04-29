# Plugins are required to specify the BST_MIN_VERSION
from buildstream import Source


class NoMinVersion(Source):
    pass


def setup():
    return NoMinVersion
