from buildstream import Source, SourceError, Consistency


class ConsistencyErrorSource(Source):

    def configure(self, node):
        pass

    def preflight(self):
        pass

    def get_unique_key(self):
        return {}

    def get_consistency(self):

        # Raise an error unconditionally
        raise SourceError("Something went terribly wrong",
                          reason="the-consistency-error")

    def get_ref(self):
        return None

    def set_ref(self, ref, node):
        pass

    def fetch(self):
        pass

    def stage(self, directory):
        pass


def setup():
    return ConsistencyErrorSource
