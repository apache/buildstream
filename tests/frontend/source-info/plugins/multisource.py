from buildstream import Node, Source


class MultiSource(Source):
    BST_MIN_VERSION = "2.0"

    BST_CUSTOM_SOURCE_PROVENANCE = True

    def configure(self, node):
        pass

    def preflight(self):
        pass

    def get_unique_key(self):
        return {}

    def load_ref(self, node):
        pass

    def get_ref(self):
        return {}

    def set_ref(self, ref, node):
        pass

    def is_cached(self):
        return False

    def collect_source_info(self):
        return [
            self.create_source_info(
                "http://ponyfarm.com/ponies", "pony-ride", "pony-age", "1234567", version_guess="12"
            ),
            self.create_source_info(
                "http://ponyfarm.com/happy",
                "pony-ride",
                "pony-age",
                "1234567",
                version_guess="12",
                provenance_node=Node.from_dict({"homepage": "http://happy.ponyfarm.com"}),
            ),
        ]


# Plugin entry point
def setup():
    return MultiSource
