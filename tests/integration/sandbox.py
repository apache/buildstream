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
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream.testing._utils.site import HAVE_SANDBOX


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_sandbox_shm(cli, datafiles):
    project = str(datafiles)
    element_name = "sandbox/test-dev-shm.bst"

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0


# Test that variable expansion works in build-arch sandbox config.
# Regression test for https://gitlab.com/BuildStream/buildstream/-/issues/1303
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_build_arch(cli, datafiles):
    project = str(datafiles)
    element_name = "sandbox/build-arch.bst"

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0
