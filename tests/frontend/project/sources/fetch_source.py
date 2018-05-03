import os
import sys

from buildstream import Source, Consistency, SourceError

# Expected config
# sources:
# - output-text: $FILE
#   urls:
#   - foo:bar
#   - baz:quux
#   fetch-succeeds:
#     Foo/bar: true
#     ooF/bar: false


class FetchSource(Source):
    # Read config to know which URLs to fetch
    def configure(self, node):
        self.original_urls = self.node_get_member(node, list, 'urls')
        self.urls = [self.translate_url(url) for url in self.original_urls]
        self.output_file = self.node_get_member(node, str, 'output-text')
        self.fetch_succeeds = {}
        if 'fetch-succeeds' in node:
            self.fetch_succeeds = {x[0]: x[1] for x in self.node_items(node['fetch-succeeds'])}
        self.urls_cached = False

    def preflight(self):
        output_dir = os.path.dirname(self.output_file)
        if not os.path.exists(output_dir):
            raise SourceError("Directory '{}' does not exist".format(output_dir))

    def get_unique_key(self):
        return {"urls": self.original_urls, "output_file": self.output_file}

    def get_consistency(self):
        if not os.path.exists(self.output_file):
            return Consistency.RESOLVED

        all_fetched = True
        with open(self.output_file, "r") as f:
            contents = f.read()
            for url in self.original_urls:
                if url not in contents:
                    return Consistency.RESOLVED

        return Consistency.CACHED

    # We dont have a ref, we're a local file...
    def load_ref(self, node):
        pass

    def get_ref(self):
        return None  # pragma: nocover

    def set_ref(self, ref, node):
        pass  # pragma: nocover

    def fetch(self):
        with open(self.output_file, "a") as f:
            for i, url in enumerate(self.urls):
                origin_url = self.original_urls[i]
                success = url in self.fetch_succeeds and self.fetch_succeeds[url]
                message = "Fetch {} {} from {}\n".format(origin_url,
                                                         "succeeded" if success else "failed",
                                                         url)
                f.write(message)
                if not success:
                    raise SourceError("Failed to fetch {}".format(url))


def setup():
    return FetchSource
