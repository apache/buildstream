import os
import pytest
import pkg_resources


# A mock setuptools dist object.
class MockDist:
    def __init__(self, datafiles, module_name):
        self.datafiles = datafiles
        self.module_name = module_name

    def get_resource_filename(self, *_args, **_kwargs):
        return os.path.join(self.datafiles.dirname, self.datafiles.basename, self.module_name)


# A mock setuptools entry object.
class MockEntry:
    def __init__(self, datafiles, module_name):
        self.dist = MockDist(datafiles, module_name)
        self.module_name = module_name


# Patch setuptools.get_entry_info
#
# Use result = entry_fixture(datafiles, entry_point, lookup_string) to
# patch setuptools for external plugin loading.
#
@pytest.fixture()
def entry_fixture(monkeypatch):
    def patch(datafiles, entry_point, lookup_string):
        dist, package = lookup_string.split(":")

        def mock_entry(pdist, pentry_point, ppackage):
            assert pdist == dist
            assert pentry_point == entry_point
            assert ppackage == package

            return MockEntry(datafiles, package)

        monkeypatch.setattr(pkg_resources, "get_entry_info", mock_entry)

    return patch
