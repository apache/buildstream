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

from buildstream._testing import cli_remote_execution as cli  # pylint: disable=unused-import
from buildstream._testing.integration import assert_contains

from tests.testutils.site import pip_sample_packages  # pylint: disable=unused-import
from tests.testutils.site import SAMPLE_PACKAGES_SKIP_REASON


pytestmark = pytest.mark.remotecache


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")

# Test building an executable with a remote cache:
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif("not pip_sample_packages()", reason=SAMPLE_PACKAGES_SKIP_REASON)
def test_remote_autotools_build(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    element_name = "autotools/amhello.bst"

    result = cli.run(project=project, args=["build", element_name])
    result.assert_success()
    assert element_name in result.get_pushed_elements()

    result = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    result.assert_success()

    assert_contains(
        checkout,
        [
            "/usr",
            "/usr/lib",
            "/usr/bin",
            "/usr/share",
            "/usr/bin/hello",
            "/usr/share/doc",
            "/usr/share/doc/amhello",
            "/usr/share/doc/amhello/README",
        ],
    )

    # then remove it locally
    result = cli.run(project=project, args=["artifact", "delete", element_name])
    result.assert_success()

    result = cli.run(project=project, args=["build", element_name])
    result.assert_success()
    assert element_name in result.get_pulled_elements()


# Test building an executable with a remote cache:
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif("not pip_sample_packages()", reason=SAMPLE_PACKAGES_SKIP_REASON)
def test_remote_autotools_build_no_cache(cli, datafiles):
    project = str(datafiles)
    element_name = "autotools/amhello.bst"

    cli.configure({"artifacts": {"servers": [{"url": "http://fake.url.service", "push": True}]}})
    result = cli.run(project=project, args=["build", element_name])
    result.assert_success()

    assert """WARNING Failed to initialize remote""" in result.stderr
    assert """Remote initialisation failed with status UNAVAILABLE: DNS resolution failed""" in result.stderr
