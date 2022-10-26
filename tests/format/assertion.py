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
from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream._testing.runcli import cli  # pylint: disable=unused-import

# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "assertion")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target,opt_pony,opt_horsy,assertion",
    [
        # Test an unconditional (!) directly in the element
        ("raw-assertion.bst", "False", "False", "Raw assertion boogey"),
        # Test an assertion in a conditional
        ("conditional-assertion.bst", "True", "False", "It's not pony time yet"),
        # Test that we get the first composited assertion
        ("ordered-assertion.bst", "True", "True", "It's not horsy time yet"),
    ],
)
def test_assertion_cli(cli, datafiles, target, opt_pony, opt_horsy, assertion):
    project = str(datafiles)
    result = cli.run(
        project=project,
        silent=True,
        args=[
            "--option",
            "pony",
            opt_pony,
            "--option",
            "horsy",
            opt_horsy,
            "show",
            "--deps",
            "none",
            "--format",
            "%{vars}",
            target,
        ],
    )
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.USER_ASSERTION)

    # Assert that the assertion text provided by the user
    # is found in the exception text
    assert assertion in str(result.exception)
