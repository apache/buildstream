from buildstream import Source


class Sample(Source):
    BST_MIN_VERSION = "2.0"

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
            )
        ]


# Plugin entry point
def setup():
    return Sample
