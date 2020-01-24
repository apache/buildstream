#
#  Copyright (C) 2018 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.exceptions import ErrorDomain
from buildstream import _yaml
from buildstream.testing import cli_remote_execution as cli  # pylint: disable=unused-import

pytestmark = pytest.mark.remoteexecution

# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project",)


@pytest.mark.datafiles(DATA_DIR)
def test_build_remote_failure(cli, datafiles):
    project = str(datafiles)
    element_path = os.path.join(project, "elements", "element.bst")
    checkout_path = os.path.join(cli.directory, "checkout")

    # Write out our test target
    element = {
        "kind": "script",
        "depends": [{"filename": "base.bst", "type": "build",},],
        "config": {"commands": ["touch %{install-root}/foo", "false",],},
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
