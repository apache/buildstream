from buildstream import Source


class ConsistencyBugSource(Source):

    BST_MIN_VERSION = "2.0"

    def configure(self, node):
        pass

    def preflight(self):
        pass

    def get_unique_key(self):
        return {}

    def is_resolved(self):
        return True

    def is_cached(self):

        # Raise an unhandled exception (not a BstError)
        raise Exception("Something went terribly wrong")

    def get_ref(self):
        return None

    def set_ref(self, ref, node):
        pass

    def fetch(self, **kwargs):
        pass

    def stage(self, directory):
        pass


def setup():
    return ConsistencyBugSource
