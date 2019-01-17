from buildstream import Element


class FooElement(Element):

    def preflight(self):
        pass

    def configure(self, node):
        pass

    def get_unique_key(self):
        return {}


def setup():
    return FooElement
