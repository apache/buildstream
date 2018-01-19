from buildstream import Source, SourceError, Consistency


class PreflightErrorSource(Source):

    def configure(self, node):
        pass

    def preflight(self):

        # Raise an untyped exception unconditionally.
        # This is expected not to be handled and should test the behaviour of
        # unhandled exceptions going off in the main buildstream application.
        raise Exception("preflighterror: Unsatisfied requirements in preflight, raising this error")

    def get_unique_key(self):
        return {}

    def get_consistency(self):
        return Consistency.CACHED

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
