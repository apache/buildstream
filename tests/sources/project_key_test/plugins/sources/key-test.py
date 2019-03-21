from buildstream import Source, Consistency


class KeyTest(Source):
    """ This plugin should fail if get_unique_key is called before track
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ref = False

    def preflight(self):
        pass

    def configure(self, node):
        pass

    def get_unique_key(self):
        assert self.ref
        return "abcdefg"

    def get_consistency(self):
        if self.ref:
            return Consistency.RESOLVED
        else:
            return Consistency.INCONSISTENT

    def load_ref(self, node):
        pass

    def get_ref(self):
        pass

    def set_ref(self, ref, node):
        pass

    def track(self, **kwargs):
        self.ref = True

    def fetch(self, **kwargs):
        pass

    def stage(self, directory):
        pass


def setup():
    return KeyTest
