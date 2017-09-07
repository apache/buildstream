from buildstream import Source, Consistency


class CustomSource(Source):

    def configure(self, node):
        print("Source Data: %s" % node)
        self.node_validate(node, ['configuration'] + Source.COMMON_CONFIG_KEYS)
        self.configuration = self.node_get_member(node, str, "configuration")

    def preflight(self):
        pass

    def get_unique_key(self):
        return self.configuration

    def get_consistency(self):
        return Consistency.INCONSISTENT

    def refresh(self, node):
        return False

    def fetch(self):
        pass

    def stage(self, directory):
        pass


def setup():
    return CustomSource
