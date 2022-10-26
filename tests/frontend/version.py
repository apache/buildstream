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

from buildstream._testing.runcli import cli  # pylint: disable=unused-import


# For utils.get_bst_version()
from buildstream import utils


def assert_version(cli_version_output):
    major, minor = utils.get_bst_version()
    expected_start = "{}.{}".format(major, minor)
    if not cli_version_output.startswith(expected_start):
        raise AssertionError(
            "Version output expected to begin with '{}',".format(expected_start)
            + " output was: {}".format(cli_version_output)
        )


def test_version(cli):
    result = cli.run(args=["--version"])
    result.assert_success()
    assert_version(result.output)
