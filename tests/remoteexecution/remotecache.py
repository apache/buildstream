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

import copy
import os
import pytest

from buildstream.exceptions import ErrorDomain
from buildstream._testing import cli_remote_execution as cli  # pylint: disable=unused-import
from buildstream._testing.integration import assert_contains
from tests.testutils.site import pip_sample_packages  # pylint: disable=unused-import
from tests.testutils.site import SAMPLE_PACKAGES_SKIP_REASON


pytestmark = pytest.mark.remoteexecution


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


# Test building an executable with remote-execution and remote-cache enabled
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif("not pip_sample_packages()", reason=SAMPLE_PACKAGES_SKIP_REASON)
def test_remote_autotools_build(cli, datafiles, remote_services):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    element_name = "autotools/amhello.bst"

    services = cli.ensure_services()
    assert set(services) == set(["action-cache", "execution", "storage"])

    # Enable remote cache and remove explicit remote execution CAS configuration.
    config_without_remote_cache = copy.deepcopy(cli.config)
    cli.configure({"cache": {"storage-service": {"url": remote_services.storage_service}}})
    del cli.config["remote-execution"]["storage-service"]
    config_with_remote_cache = cli.config

    # Build element with remote execution.
    result = cli.run(project=project, args=["build", element_name])
    result.assert_success()

    # Attempt checkout from local cache by temporarily disabling remote cache.
    # This should fail as the build result shouldn't have been downloaded to the local cache.
    cli.config = config_without_remote_cache
    result = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    result.assert_main_error(ErrorDomain.STREAM, "uncached-checkout-attempt")
    cli.config = config_with_remote_cache

    # Attempt checkout again with remote cache.
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
