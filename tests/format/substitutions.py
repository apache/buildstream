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
from buildstream._testing import cli  # pylint: disable=unused-import


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project", "default")


# Test that output is formatted correctly, when there are multiple matches of a
# variable that is known to BuildStream.
#
@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_match_multiple(cli, datafiles):
    project = str(datafiles)
    result = cli.run(project=project, args=["show", "--format", "%{name} {name} %{name}", "manual.bst"])
    result.assert_success()
    assert result.output == "manual.bst {name} manual.bst\n"
