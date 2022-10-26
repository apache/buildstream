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

from buildstream.exceptions import ErrorDomain
from buildstream import _yaml
from buildstream._testing import cli_remote_execution as cli  # pylint: disable=unused-import
from tests.testutils.site import pip_sample_packages  # pylint: disable=unused-import
from tests.testutils.site import SAMPLE_PACKAGES_SKIP_REASON

pytestmark = pytest.mark.remoteexecution

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif("not pip_sample_packages()", reason=SAMPLE_PACKAGES_SKIP_REASON)
def test_build_remote_failure(cli, datafiles):
    project = str(datafiles)
    element_path = os.path.join(project, "elements", "element.bst")
    checkout_path = os.path.join(cli.directory, "checkout")

    # Write out our test target
    element = {
        "kind": "script",
        "depends": [
            {
                "filename": "base.bst",
                "type": "build",
            },
        ],
        "config": {
            "commands": [
                "touch %{install-root}/foo",
                "false",
            ],
        },
    }
    _yaml.roundtrip_dump(element, element_path)

    services = cli.ensure_services()
    assert set(services) == set(["action-cache", "execution", "storage"])

    # Try to build it, this should result in a failure that contains the content
    result = cli.run(project=project, args=["build", "element.bst"])
    result.assert_main_error(ErrorDomain.STREAM, None)

    result = cli.run(project=project, args=["artifact", "checkout", "element.bst", "--directory", checkout_path])
    result.assert_success()

    # check that the file created before the failure exists
    filename = os.path.join(checkout_path, "foo")
    assert os.path.isfile(filename)
