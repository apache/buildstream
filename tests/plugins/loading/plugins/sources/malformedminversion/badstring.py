# Plugins are required to specify the BST_MIN_VERSION
from buildstream import Source


class MalformedMinVersion(Source):

    BST_MIN_VERSION = "1.pony"


def setup():
    return MalformedMinVersion
