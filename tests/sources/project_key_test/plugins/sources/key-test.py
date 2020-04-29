import os

from buildstream import Source


class KeyTest(Source):
    """ This plugin should fail if get_unique_key is called before track
    """

    BST_MIN_VERSION = "2.0"

    def preflight(self):
        pass

    def configure(self, node):
        if node.get_scalar("ref", None).is_none():
            self.ref = None
        else:
            self.ref = True

    def get_unique_key(self):
        assert self.ref
        return "abcdefg"

    def is_cached(self):
        return False

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
