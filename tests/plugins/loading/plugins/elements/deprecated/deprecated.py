from buildstream import Element


class Deprecated(Element):
    BST_MIN_VERSION = "2.0"
    BST_PLUGIN_DEPRECATED = True
    BST_PLUGIN_DEPRECATION_MESSAGE = "Here is some detail."

    def configure(self, node):
        pass

    def preflight(self):
        pass

    def get_unique_key(self):
        return {}


# Plugin entry point
def setup():
    return Deprecated
