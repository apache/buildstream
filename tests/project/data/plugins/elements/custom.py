from buildstream import Element


class CustomElement(Element):

    def configure(self, node):
        print("Element Data: {}".format(node))
        self.node_validate(node, ['configuration'])
        self.configuration = self.node_subst_member(node, "configuration", '')

    def preflight(self):
        pass

    def get_unique_key(self):
        return self.configuration


def setup():
    return CustomElement
