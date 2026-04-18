import os

from buildstream import Source, SourceError

# Expected config
# sources:
# - output-text: $FILE
#   url: foo:bar
#   fetch-succeeds:
#     Foo/bar: true
#     ooF/bar: false


class FetchSource(Source):

    BST_MIN_VERSION = "2.0"

    # Read config to know which URL to fetch
    def configure(self, node):
        self.original_url = node.get_str("url")
        self.output_file = node.get_str("output-text")
        self.fetch_succeeds = {key: value.as_bool() for key, value in node.get_mapping("fetch-succeeds", {}).items()}

        self.mark_download_url(self.original_url)

    def preflight(self):
        output_dir = os.path.dirname(self.output_file)
        if not os.path.exists(output_dir):
            raise SourceError("Directory '{}' does not exist".format(output_dir))

    def stage(self, directory):
        pass

    def fetch(self):
        url = self.translate_url(self.original_url)
        with open(self.output_file, "a") as f:
            success = url in self.fetch_succeeds and self.fetch_succeeds[url]
            message = "Fetch {} {} from {}\n".format(self.original_url, "succeeded" if success else "failed", url)
            f.write(message)
            if not success:
                raise SourceError("Failed to fetch {}".format(url))

    def get_unique_key(self):
        return {"url": self.original_url, "output_file": self.output_file}

    def is_resolved(self):
        return True

    def is_cached(self) -> bool:
        if not os.path.exists(self.output_file):
            return False

        with open(self.output_file, "r") as f:
            contents = f.read()
            if self.original_url not in contents:
                return False

        return True

    # We dont have a ref, we're a local file...
    def load_ref(self, node):
        pass

    def get_ref(self):
        return None  # pragma: nocover

    def set_ref(self, ref, node):
        pass  # pragma: nocover


def setup():
    return FetchSource
