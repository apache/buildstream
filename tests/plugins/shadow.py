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

#
# This test case ensures that user provided plugins appropriately shadow
# core defined plugins, which is a behavior that is required in order to
# make it safe for BuildStream to add more plugins in the future without
# stomping on plugin namespace.
#

import os
import pytest

from buildstream._testing import cli  # pylint: disable=unused-import
from buildstream import _yaml


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "shadow")


def update_project(project_path, updated_configuration):
    project_conf_path = os.path.join(project_path, "project.conf")
    project_conf = _yaml.roundtrip_load(project_conf_path)

    project_conf.update(updated_configuration)

    _yaml.roundtrip_dump(project_conf, project_conf_path)


#
# Run the test with and without shadowing the "manual" plugin.
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("shadow", [True, False], ids=["shadowed", "not-shadowed"])
def test_manual(cli, datafiles, shadow):
    project = str(datafiles)

    if shadow:
        update_project(project, {"plugins": [{"origin": "local", "path": "plugins", "elements": ["manual"]}]})

    result = cli.run(project=project, args=["show", "manual.bst"])
    result.assert_success()

    if shadow:
        assert "This is an overridden manual element" in result.stderr
    else:
        assert "This is an overridden manual element" not in result.stderr
