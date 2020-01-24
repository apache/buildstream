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

from buildstream import _yaml
from buildstream.exceptions import ErrorDomain
from buildstream.testing import cli  # pylint: disable=unused-import

pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


@pytest.mark.datafiles(DATA_DIR)
def test_fallback_platform_fails(cli, datafiles):
    project = str(datafiles)
    element_path = os.path.join(project, "elements", "element.bst")

    # Write out our test target
    element = {
        "kind": "script",
        "depends": [{"filename": "base.bst", "type": "build",},],
        "config": {"commands": ["true",],},
    }
    _yaml.roundtrip_dump(element, element_path)

    result = cli.run(
        project=project,
        args=["build", "element.bst"],
        env={"BST_FORCE_BACKEND": "fallback", "BST_FORCE_SANDBOX": None},
    )
    result.assert_main_error(ErrorDomain.STREAM, None)
    assert "FallBack platform only implements dummy sandbox" in result.stderr
    # The dummy sandbox can not build the element but it can get the element read
    # There for the element should be `buildable` rather than `waiting`
    assert cli.get_element_state(project, "element.bst") == "buildable"


@pytest.mark.datafiles(DATA_DIR)
def test_fallback_platform_can_use_dummy(cli, datafiles):
    project = str(datafiles)

    result = cli.run(
        project=project,
        args=["build", "import-file1.bst"],
        env={"BST_FORCE_BACKEND": "fallback", "BST_FORCE_SANDBOX": None},
    )
    result.assert_success()
    # The fallback platform can still provide a dummy sandbox that alows simple elemnts that do not need
    # a full sandbox to still be built on new platforms.
