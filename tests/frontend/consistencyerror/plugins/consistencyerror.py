from buildstream import Source, SourceError


class ConsistencyErrorSource(Source):

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

        # Raise an error unconditionally
        raise SourceError("Something went terribly wrong", reason="the-consistency-error")

    def get_ref(self):
        return None

    def set_ref(self, ref, node):
        pass

    def fetch(self, **kwargs):
        pass

    def stage(self, directory):
        pass


def setup():
    return ConsistencyErrorSource
