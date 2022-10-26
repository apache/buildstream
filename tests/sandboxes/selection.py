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

from buildstream import utils, _yaml
from buildstream.exceptions import ErrorDomain
from buildstream._testing import cli  # pylint: disable=unused-import

pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


@pytest.mark.datafiles(DATA_DIR)
def test_dummy_sandbox_fallback(cli, datafiles, tmp_path):
    # Create symlink to buildbox-casd to work with custom PATH
    buildbox_casd = tmp_path.joinpath("bin/buildbox-casd")
    buildbox_casd.parent.mkdir()
    os.symlink(utils._get_host_tool_internal("buildbox-casd", search_subprojects_dir="buildbox"), str(buildbox_casd))

    project = str(datafiles)
    element_path = os.path.join(project, "elements", "element.bst")

    # Write out our test target
    element = {
        "kind": "script",
        "depends": [
            {
                "filename": "base.bst",
                "type": "build",
            },
        ],
        "config": {
            "commands": [
                "true",
            ],
        },
    }
    _yaml.roundtrip_dump(element, element_path)

    # Build without access to host tools, this will fail
    result = cli.run(
        project=project,
        args=["build", "element.bst"],
        env={"PATH": str(tmp_path.joinpath("bin"))},
    )
    # But if we dont spesify a sandbox then we fall back to dummy, we still
    # fail early but only once we know we need a facny sandbox and that
    # dumy is not enough, there for element gets fetched and so is buildable

    result.assert_task_error(ErrorDomain.SANDBOX, "unavailable-local-sandbox")
    assert cli.get_element_state(project, "element.bst") == "buildable"
