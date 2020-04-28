from buildstream import Source


# Just a dummy plugin which does not support the new load_ref() method.
#
# Use this to test that the core behaves as expected with such plugins.
#
class NoLoadRefSource(Source):

    BST_MIN_VERSION = "2.0"

    def configure(self, node):
        pass

    def preflight(self):
        pass

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
    return NoLoadRefSource
