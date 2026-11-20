# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# pylint: disable=redefined-outer-name
import os

import pytest

from buildstream._testing import cli  # pylint: disable=unused-import

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "artifact_list_contents")


@pytest.mark.datafiles(DATA_DIR)
def test_element_provides(cli, datafiles):
    project = str(datafiles)
    for target in ["import-bin.bst", "another.bst"]:
        if target == "another.bst":
            with open(os.path.join(project, "elements", target), "w", encoding="utf-8") as f:
                f.write("kind: import\nsources:\n- kind: local\n  path: files/bin-files\n")
        result = cli.run(project=project, args=["build", target])
        result.assert_success()

    for pattern, expected in [
        ("hello", ["another.bst", "import-bin.bst"]),
        ("usr/bin/hello", ["another.bst", "import-bin.bst"]),
        ("*/he*", ["another.bst", "import-bin.bst"]),
        ("usr/bin", []),
        ("missing", []),
    ]:
        result = cli.run(project=project, args=["element-provides", pattern])
        result.assert_success()
        assert result.output.splitlines() == expected
        assert "without locally cached artifacts" in result.stderr
