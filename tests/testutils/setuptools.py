#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
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
