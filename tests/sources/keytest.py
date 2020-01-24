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
#
#  Authors:
#        Raoul Hidalgo Charman <raoul.hidalgocharman@codethink.co.uk>
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import ErrorDomain
from buildstream.testing import cli  # pylint: disable=unused-import

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project_key_test")


# using the key-test plugin to ensure get_unique_key is never called before
# refs are resolved
@pytest.mark.datafiles(DATA_DIR)
def test_generate_key(cli, datafiles):
    project_dir = str(datafiles)

    # check that we don't fail if not tracking due to get_unique_key
    res = cli.run(project=project_dir, args=["build", "key-test.bst"])
    res.assert_main_error(ErrorDomain.PIPELINE, "inconsistent-pipeline")

    assert cli.get_element_state(project_dir, "key-test.bst") == "no reference"
    res = cli.run(project=project_dir, args=["source", "track", "key-test.bst"])
    res.assert_success()
    assert cli.get_element_state(project_dir, "key-test.bst") == "fetch needed"

    res = cli.run(project=project_dir, args=["build", "key-test.bst"])
    res.assert_success()
    assert cli.get_element_state(project_dir, "key-test.bst") == "cached"
