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

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest
import json

from buildstream._testing import cli  # pylint: disable=unused-import


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
)

def _element_by_name(elements, name):
    for element in elements:
        if element["name"] == name:
            return element


@pytest.mark.datafiles(os.path.join(DATA_DIR, "simple"))
def test_inspect_basic(cli, datafiles):
    project = str(datafiles)
    result = cli.run(project=project, silent=True, args=["inspect"])
    result.assert_success()
    output = json.loads(result.output)
    assert(output["project"]["name"] == "test")
    element = _element_by_name(output["elements"], "import-bin.bst")
    source = element["sources"][0]
    assert(source["kind"] == "local")
    assert(source["url"] == "files/bin-files")


@pytest.mark.datafiles(os.path.join(DATA_DIR, "simple"))
def test_inspect_element_glob(cli, datafiles):
    project = str(datafiles)
    result = cli.run(project=project, silent=True, args=["inspect", "*.bst"])
    result.assert_success()
    json.loads(result.output)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "source-fetch"))
def test_inspect_with_state(cli, datafiles):
    project = str(datafiles)
    result = cli.run(project=project, silent=True, args=["inspect", "--state", "--deps", "all"])
    result.assert_success()
    json.loads(result.output)
