import os

from buildstream import Source, SourceError, SourceFetcher

# Expected config
# sources:
# - output-text: $FILE
#   urls:
#   - foo:bar
#   - baz:quux
#   fetch-succeeds:
#     Foo/bar: true
#     ooF/bar: false


class FetchFetcher(SourceFetcher):
    def __init__(self, source, url, primary=False):
        super().__init__()
        self.source = source
        self.original_url = url
        self.primary = primary
        self.mark_download_url(url)

    def fetch(self, alias_override=None):
        url = self.source.translate_url(self.original_url, alias_override=alias_override, primary=self.primary)
        with open(self.source.output_file, "a") as f:
            success = url in self.source.fetch_succeeds and self.source.fetch_succeeds[url]
            message = "Fetch {} {} from {}\n".format(self.original_url, "succeeded" if success else "failed", url)
            f.write(message)
            if not success:
                raise SourceError("Failed to fetch {}".format(url))


class FetchSource(Source):

    BST_MIN_VERSION = "2.0"

    # Read config to know which URLs to fetch
    def configure(self, node):
        self.original_urls = node.get_str_list("urls")
        self.output_file = node.get_str("output-text")
        self.fetch_succeeds = {key: value.as_bool() for key, value in node.get_mapping("fetch-succeeds", {}).items()}

        # First URL is the primary one for this test
        #
        primary = True
        self.fetchers = []
        for url in self.original_urls:
            self.mark_download_url(url, primary=primary)
            fetcher = FetchFetcher(self, url, primary=primary)
            self.fetchers.append(fetcher)
            primary = False

    def get_source_fetchers(self):
        return self.fetchers

    def preflight(self):
        output_dir = os.path.dirname(self.output_file)
        if not os.path.exists(output_dir):
            raise SourceError("Directory '{}' does not exist".format(output_dir))

    def stage(self, directory):
        pass

    def fetch(self):
        for fetcher in self.fetchers:
            fetcher.fetch()

    def get_unique_key(self):
        return {"urls": self.original_urls, "output_file": self.output_file}

    def is_resolved(self):
        return True

    def is_cached(self) -> bool:
        if not os.path.exists(self.output_file):
            return False

        with open(self.output_file, "r") as f:
            contents = f.read()
            for url in self.original_urls:
                if url not in contents:
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
