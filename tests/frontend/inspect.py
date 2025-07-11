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
from dataclasses import dataclass

from buildstream._testing import cli  # pylint: disable=unused-import


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
)

# check to see if a source exists in an element
@dataclass
class _Source:
    name: str # element name
    kind: str
    version: str

def _element_by_name(elements, name):
    for element in elements:
        if element["name"] == name:
            return element

def _assert_has_elements(elements, expected):
    n_elements = len(elements)
    n_expected = len(expected)
    if len(elements) != len(expected):
        raise Exception(f"Expected {n_expected} elements, got {n_elements}")
    for expected_name in expected:
        if _element_by_name(elements, expected_name) is None:
            raise Exception(f"Element {expected_name} is missing")

def _assert_has_source(elements, expected: _Source):
    element = _element_by_name(elements, expected.name)
    if element is None:
        raise Exception(f"Cannot find element {expected.name}")
    if "sources" in element:
        for source in element["sources"]:
            kind = source["kind"]
            version = source["version"]
            if kind == expected.kind and version == expected.version:
                return
    raise Exception(f"Element {expected.name} does not contain the expected source")

 
@pytest.mark.parametrize(
    "flags,elements",
    [
        ([], ["import-dev.bst", "import-bin.bst", "compose-all.bst", "target.bst", "subdir/target.bst"]),
        (["*.bst", "**/*.bst"], ["import-dev.bst", "import-bin.bst", "compose-all.bst", "target.bst", "subdir/target.bst"]),
        (["--state"], ["import-dev.bst", "import-bin.bst", "compose-all.bst", "target.bst", "subdir/target.bst"]),
        (["--state", "--deps", "all"], ["import-dev.bst", "import-bin.bst", "compose-all.bst", "target.bst", "subdir/target.bst"]),
        (["subdir/*.bst"], ["import-dev.bst", "subdir/target.bst"])
    ],
)
@pytest.mark.datafiles(os.path.join(DATA_DIR, "simple"))
def test_inspect_simple(cli, datafiles, flags, elements):
    project = str(datafiles)
    result = cli.run(project=project, silent=True, args=["inspect"] + flags)
    output = json.loads(result.output)
    _assert_has_elements(output["elements"], elements)


@pytest.mark.parametrize(
    "flags,sources",
    [
        ([], [
            _Source(name="tar-custom-version.bst", kind="tar", version="9d0c936c78d0dfe3a67cae372c9a2330476ea87a2eec16b2daada64a664ca501"),
            _Source(name="extradata.bst", kind="extradata", version="1234567")
        ]),
    ],
)
@pytest.mark.datafiles(os.path.join(DATA_DIR, "source-info"))
def test_inspect_sources(cli, datafiles, flags, sources):
    project = str(datafiles)
    result = cli.run(project=project, silent=True, args=["inspect"] + flags)
    output = json.loads(result.output)
    [_assert_has_source(output["elements"], source) for source in sources]
