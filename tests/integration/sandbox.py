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
from buildstream._testing._utils.site import HAVE_SANDBOX


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_sandbox_shm(cli, datafiles):
    project = str(datafiles)
    element_name = "sandbox/test-dev-shm.bst"

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0


# Test that variable expansion works in build-arch sandbox config.
# Regression test for https://gitlab.com/BuildStream/buildstream/-/issues/1303
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_build_arch(cli, datafiles):
    project = str(datafiles)
    element_name = "sandbox/build-arch.bst"

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0
