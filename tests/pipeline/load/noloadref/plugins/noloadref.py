from buildstream import Source, Consistency


# Just a dummy plugin which does not support the new load_ref() method.
#
# Use this to test that the core behaves as expected with such plugins.
#
class NoLoadRefSource(Source):

    def configure(self, node):
        pass

    def preflight(self):
        pass

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
    return NoLoadRefSource
