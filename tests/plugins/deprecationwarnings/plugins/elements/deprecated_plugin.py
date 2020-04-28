from buildstream import BuildElement


class DeprecatedPlugin(BuildElement):
    BST_MIN_VERSION = "2.0"
    BST_PLUGIN_DEPRECATED = True
    BST_PLUGIN_DEPRECATION_MESSAGE = "Here is some detail."


# Plugin entry point
def setup():
    return DeprecatedPlugin
