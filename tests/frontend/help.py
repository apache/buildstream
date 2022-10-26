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

import pytest
from buildstream._testing.runcli import cli  # pylint: disable=unused-import


def assert_help(cli_output):
    expected_start = "Usage: "
    if not cli_output.startswith(expected_start):
        raise AssertionError(
            "Help output expected to begin with '{}',".format(expected_start) + " output was: {}".format(cli_output)
        )


def test_help_main(cli):
    result = cli.run(args=["--help"])
    result.assert_success()
    assert_help(result.output)


@pytest.mark.parametrize("command", [("artifact"), ("build"), ("shell"), ("show"), ("source"), ("workspace")])
def test_help(cli, command):
    result = cli.run(args=[command, "--help"])
    result.assert_success()
    assert_help(result.output)
