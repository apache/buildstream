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

from buildstream import _yaml

from buildstream._testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream._testing.integration import walk_dir


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


def create_import_element(name, path, source, target, source_path):
    element = {
        "kind": "import",
        "sources": [{"kind": "local", "path": source_path}],
        "config": {"source": source, "target": target},
    }
    os.makedirs(os.path.dirname(os.path.join(path, name)), exist_ok=True)
    _yaml.roundtrip_dump(element, os.path.join(path, name))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "source,target,path,expected",
    [
        ("/", "/", "files/import-source", ["/test.txt", "/subdir", "/subdir/test.txt"]),
        ("/subdir", "/", "files/import-source", ["/test.txt"]),
        ("/", "/", "files/import-source/subdir", ["/test.txt"]),
        (
            "/",
            "/output",
            "files/import-source",
            ["/output", "/output/test.txt", "/output/subdir", "/output/subdir/test.txt"],
        ),
    ],
)
def test_import(cli, datafiles, source, target, path, expected):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    element_path = os.path.join(project, "elements")
    element_name = "import/import.bst"

    create_import_element(element_name, element_path, source, target, path)

    res = cli.run(project=project, args=["build", element_name])
    assert res.exit_code == 0

    cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    assert res.exit_code == 0

    assert set(walk_dir(checkout)) == set(expected)
