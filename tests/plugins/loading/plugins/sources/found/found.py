from buildstream import Source


class Found(Source):
    BST_MIN_VERSION = "2.0"

    def configure(self, node):
        pass

    def preflight(self):
        pass

    def get_unique_key(self):
        return {}

    def load_ref(self, node):
        pass

    def get_ref(self):
        return {}

    def set_ref(self, ref, node):
        pass

    def is_cached(self):
        return False


# Plugin entry point
def setup():

    return Found
