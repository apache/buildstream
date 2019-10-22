import os

from buildstream import Source, Consistency


class KeyTest(Source):
    """ This plugin should fail if get_unique_key is called before track
    """

    def preflight(self):
        pass

    def configure(self, node):
        self.ref = node.get_bool("ref", False)

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
        return self.ref

    def set_ref(self, ref, node):
        node["ref"] = self.ref = ref

    def track(self, **kwargs):
        return True

    def fetch(self, **kwargs):
        pass

    def stage(self, directory):
        # Create a dummy file as output, as import elements do not allow empty
        # output. Its existence is a statement that we have staged ourselves.
        open(os.path.join(directory, "output"), "w").close()


def setup():
    return KeyTest
