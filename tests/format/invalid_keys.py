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
from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream._testing.runcli import cli  # pylint: disable=unused-import

# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "invalid-keys")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    ("element", "location"),
    [
        ("no-path-specified.bst", "line 4 column 4"),
        ("optional-source.bst", "line 6 column 10"),
        ("included-source.bst", "line 4 column 4"),
    ],
)
def test_compositied_node_fails_usefully(cli, datafiles, element, location):
    project = str(datafiles)
    result = cli.run(project=project, args=["show", element])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)

    assert "synthetic node" not in result.stderr
    assert "{} [{}]: Dictionary did not contain expected key 'path'".format(element, location) in result.stderr
