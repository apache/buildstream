from buildstream import Element


class CustomElement(Element):

    def configure(self, node):
        print("Element Data: %s" % node)
        self.configuration = self.node_subst_member(node, "configuration", default_value='')

    def preflight(self):
        pass

    def get_unique_key(self):
        return self.configuration


def setup():
    return CustomElement
