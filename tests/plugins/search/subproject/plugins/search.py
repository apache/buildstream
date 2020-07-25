from buildstream import Element, Scope


class Search(Element):
    BST_MIN_VERSION = "2.0"

    def configure(self, node):
        self.search_element_path = node.get_str("search")
        self.search_element = None

    def preflight(self):
        self.search_element = self.search(Scope.ALL, self.search_element_path)

        assert self.search_element is not None
        assert isinstance(self.search_element, Element)

    def get_unique_key(self):
        return {}


# Plugin entry point
def setup():
    return Search
