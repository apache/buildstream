#
#  Copyright (C) 2019 Bloomberg Finance LP
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
# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream import utils, _yaml
from buildstream.exceptions import ErrorDomain
from buildstream.testing import cli  # pylint: disable=unused-import

pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


@pytest.mark.datafiles(DATA_DIR)
def test_dummy_sandbox_fallback(cli, datafiles, tmp_path):
    # Create symlink to buildbox-casd to work with custom PATH
    buildbox_casd = tmp_path.joinpath("bin/buildbox-casd")
    buildbox_casd.parent.mkdir()
    os.symlink(utils.get_host_tool("buildbox-casd"), str(buildbox_casd))

    project = str(datafiles)
    element_path = os.path.join(project, "elements", "element.bst")

    # Write out our test target
    element = {
        "kind": "script",
        "depends": [{"filename": "base.bst", "type": "build",},],
        "config": {"commands": ["true",],},
    }
    _yaml.roundtrip_dump(element, element_path)

    # Build without access to host tools, this will fail
    result = cli.run(project=project, args=["build", "element.bst"], env={"PATH": str(tmp_path.joinpath("bin"))},)
    # But if we dont spesify a sandbox then we fall back to dummy, we still
    # fail early but only once we know we need a facny sandbox and that
    # dumy is not enough, there for element gets fetched and so is buildable

    result.assert_task_error(ErrorDomain.SANDBOX, "unavailable-local-sandbox")
    assert cli.get_element_state(project, "element.bst") == "buildable"
