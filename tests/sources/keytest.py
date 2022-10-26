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
#  Authors:
#        Raoul Hidalgo Charman <raoul.hidalgocharman@codethink.co.uk>
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream._testing import ErrorDomain
from buildstream._testing import cli  # pylint: disable=unused-import

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
