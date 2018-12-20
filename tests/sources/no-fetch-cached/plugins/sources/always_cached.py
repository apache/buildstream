"""
always_cached
=============

This is a test source plugin that is always cached.
Used to test that BuildStream core does not call fetch() for cached sources.

"""

from buildstream import Consistency, Source


class AlwaysCachedSource(Source):

    def configure(self, node):
        pass

    def preflight(self):
        pass

    def get_unique_key(self):
        return None

    def get_consistency(self):
        return Consistency.CACHED

    def load_ref(self, node):
        pass

    def get_ref(self):
        return None

    def set_ref(self, ref, node):
        pass

    def fetch(self):
        # Source is always cached, so fetch() should never be called
        assert False

    def stage(self, directory):
        pass


def setup():
    return AlwaysCachedSource
