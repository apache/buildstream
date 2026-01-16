from buildstream import Node, Source


class MultiSource(Source):
    BST_MIN_VERSION = "2.0"

    BST_CUSTOM_SOURCE_PROVENANCE = True

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

    def collect_source_info(self):
        return []


# Plugin entry point
def setup():
    return MultiSource
