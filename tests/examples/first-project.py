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
from buildstream._testing.integration import assert_contains
from buildstream._testing._utils.site import IS_LINUX


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "doc", "examples", "first-project")


@pytest.mark.skipif(not IS_LINUX, reason="Only available on linux")
@pytest.mark.datafiles(DATA_DIR)
def test_first_project_build_checkout(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")

    result = cli.run(project=project, args=["build", "hello.bst"])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["artifact", "checkout", "hello.bst", "--directory", checkout])
    assert result.exit_code == 0

    assert_contains(checkout, ["/hello.world"])
