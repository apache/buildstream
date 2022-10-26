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

from buildstream._testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream._testing._utils.site import HAVE_SANDBOX, BUILDBOX_RUN


pytestmark = pytest.mark.integration

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.xfail(
    HAVE_SANDBOX == "buildbox-run" and BUILDBOX_RUN == "buildbox-run-userchroot",
    reason="Custom UID/GID not supported by userchroot",
)
@pytest.mark.datafiles(DATA_DIR)
def test_build_uid_overridden(cli, datafiles):
    project = str(datafiles)
    element_name = "build-uid/build-uid.bst"

    project_config = {"name": "build-uid-test", "sandbox": {"build-uid": 800, "build-gid": 900}}

    result = cli.run_project_config(project=project, project_config=project_config, args=["build", element_name])
    assert result.exit_code == 0


@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.xfail(
    HAVE_SANDBOX == "buildbox-run" and BUILDBOX_RUN == "buildbox-run-userchroot",
    reason="Custom UID/GID not supported by userchroot",
)
@pytest.mark.datafiles(DATA_DIR)
def test_build_uid_in_project(cli, datafiles):
    project = str(datafiles)
    element_name = "build-uid/build-uid-1023.bst"

    project_config = {"name": "build-uid-test", "sandbox": {"build-uid": 1023, "build-gid": 3490}}

    result = cli.run_project_config(project=project, project_config=project_config, args=["build", element_name])
    assert result.exit_code == 0


@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.xfail(
    HAVE_SANDBOX == "buildbox-run" and BUILDBOX_RUN == "buildbox-run-userchroot",
    reason="Custom UID/GID not supported by userchroot",
)
def test_build_uid_default(cli, datafiles):
    project = str(datafiles)
    element_name = "build-uid/build-uid-default.bst"

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0
