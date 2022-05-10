from buildstream import Element


class Manual(Element):
    BST_MIN_VERSION = "2.0"

    def configure(self, node):
        self.info("This is an overridden manual element")

    def preflight(self):
        pass

    def get_unique_key(self):
        return {}


# Plugin entry point
def setup():
    return Manual
