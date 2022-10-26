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
import shutil
import pytest

from buildstream._testing import cli  # pylint: disable=unused-import
from buildstream._testing.integration import assert_contains
from buildstream._testing._utils.site import HAVE_SANDBOX, BUILDBOX_RUN


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


@pytest.mark.datafiles(os.path.join(DATA_DIR))
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.xfail(
    HAVE_SANDBOX == "buildbox-run" and BUILDBOX_RUN == "buildbox-run-userchroot",
    reason="Root directory not writable with userchroot",
)
def test_filter_pass_integration(datafiles, cli):
    project = str(datafiles)

    # Passing integration commands should build nicely
    result = cli.run(project=project, args=["build", "filter/filter.bst"])
    result.assert_success()

    # Checking out the element should work
    checkout_dir = os.path.join(project, "filter")
    result = cli.run(
        project=project,
        args=["artifact", "checkout", "--integrate", "--directory", checkout_dir, "filter/filter.bst"],
    )
    result.assert_success()

    # Check that the integration command was run
    assert_contains(checkout_dir, ["/foo"])
    shutil.rmtree(checkout_dir)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.xfail(
    HAVE_SANDBOX == "buildbox-run" and BUILDBOX_RUN == "buildbox-run-userchroot",
    reason="Root directory not writable with userchroot",
)
def test_filter_pass_integration_uncached(datafiles, cli):
    project = str(datafiles)

    # Passing integration commands should build nicely
    result = cli.run(project=project, args=["build", "filter/filter.bst"])
    result.assert_success()

    # Delete the build dependency of the filter element.
    # The built filter element should be usable even if the build dependency
    # is not available in the local cache.
    result = cli.run(project=project, args=["artifact", "delete", "filter/parent.bst"])
    result.assert_success()

    # Checking out the element should work
    checkout_dir = os.path.join(project, "filter")
    result = cli.run(
        project=project,
        args=["artifact", "checkout", "--integrate", "--directory", checkout_dir, "filter/filter.bst"],
    )
    result.assert_success()

    # Check that the integration command was run
    assert_contains(checkout_dir, ["/foo"])
    shutil.rmtree(checkout_dir)
