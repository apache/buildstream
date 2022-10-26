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
from buildstream._testing.runcli import cli  # pylint: disable=unused-import

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


@pytest.mark.parametrize("target", [("compose-include-bin.bst"), ("compose-exclude-dev.bst")])
@pytest.mark.datafiles(DATA_DIR)
def test_compose_splits(datafiles, cli, target):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")

    # First build it
    result = cli.run(project=project, args=["build", target])
    result.assert_success()

    # Now check it out
    result = cli.run(project=project, args=["artifact", "checkout", target, "--directory", checkout])
    result.assert_success()

    # Check that the executable hello file is found in the checkout
    filename = os.path.join(checkout, "usr", "bin", "hello")
    assert os.path.exists(filename)

    # Check that the executable hello file is found in the checkout
    filename = os.path.join(checkout, "usr", "include", "pony.h")
    assert not os.path.exists(filename)
