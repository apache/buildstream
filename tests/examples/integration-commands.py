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
from buildstream._testing._utils.site import IS_LINUX, MACHINE_ARCH, HAVE_SANDBOX


pytestmark = pytest.mark.integration
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "..", "..", "doc", "examples", "integration-commands"
)


@pytest.mark.skipif(MACHINE_ARCH != "x86-64", reason="Examples are written for x86-64")
@pytest.mark.skipif(not IS_LINUX or not HAVE_SANDBOX, reason="Only available on linux with sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_integration_commands_build(cli, datafiles):
    project = str(datafiles)

    result = cli.run(project=project, args=["build", "hello.bst"])
    assert result.exit_code == 0


# Test running the executable
@pytest.mark.skipif(MACHINE_ARCH != "x86-64", reason="Examples are written for x86-64")
@pytest.mark.skipif(not IS_LINUX or not HAVE_SANDBOX, reason="Only available on linux with sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_integration_commands_run(cli, datafiles):
    project = str(datafiles)

    result = cli.run(project=project, args=["build", "hello.bst"])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["shell", "hello.bst", "--", "hello", "pony"])
    assert result.exit_code == 0
    assert result.output == "Hello pony\n"
