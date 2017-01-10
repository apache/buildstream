from buildstream import Source


class CustomSource(Source):

    def configure(self, node):
        print("Source Data: %s" % node)
        self.configuration = self.node_get_member(node, str, "configuration")

    def preflight(self):
        pass

    def get_unique_key(self):
        return self.configuration

    def consistent(self):
        return True

    def refresh(self, node):
        return False

    def fetch(self):
        pass

    def stage(self, directory):
        pass


def setup():
    return CustomSource
