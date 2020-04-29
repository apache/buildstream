from buildstream import Source, SourceError


class PreflightErrorSource(Source):

    BST_MIN_VERSION = "2.0"

    def configure(self, node):
        pass

    def preflight(self):

        # Raise a preflight error unconditionally
        raise SourceError("Unsatisfied requirements in preflight, raising this error", reason="the-preflight-error")

    def get_unique_key(self):
        return {}

    def get_ref(self):
        return None

    def set_ref(self, ref, node):
        pass

    def fetch(self):
        pass

    def stage(self, directory):
        pass


def setup():
    return PreflightErrorSource
