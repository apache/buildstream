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


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "variables")


@pytest.mark.datafiles(DATA_DIR)
def test_variables_are_resolved(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected file
    assert os.path.exists(os.path.join(checkoutdir, "file.txt"))


@pytest.mark.datafiles(DATA_DIR)
def test_handles_unresolved_variables(cli, tmpdir, datafiles):
    project = str(datafiles)

    result = cli.run(project=project, args=["build", "unresolveable-target.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.UNRESOLVED_VARIABLE)
