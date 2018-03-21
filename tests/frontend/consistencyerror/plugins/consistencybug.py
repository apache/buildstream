from buildstream import Source, SourceError, Consistency


class ConsistencyBugSource(Source):

    def configure(self, node):
        pass

    def preflight(self):
        pass

    def get_unique_key(self):
        return {}

    def get_consistency(self):

        # Raise an unhandled exception (not a BstError)
        raise Exception("Something went terribly wrong")

    def get_ref(self):
        return None

    def set_ref(self, ref, node):
        pass

    def fetch(self):
        pass

    def stage(self, directory):
        pass


def setup():
    return ConsistencyBugSource
