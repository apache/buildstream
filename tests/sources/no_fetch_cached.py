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
from buildstream._testing import create_repo
from buildstream._testing import generate_element

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "no-fetch-cached")


##################################################################
#                              Tests                             #
##################################################################
# Test that fetch() is not called for cached sources
@pytest.mark.datafiles(DATA_DIR)
def test_no_fetch_cached(cli, tmpdir, datafiles):
    project = str(datafiles)

    # Create the repo from 'files' subdir
    repo = create_repo("tar", str(tmpdir))
    ref = repo.create(os.path.join(project, "files"))

    # Write out test target with a cached and a non-cached source
    element = {"kind": "import", "sources": [repo.source_config(ref=ref), {"kind": "always_cached"}]}
    generate_element(project, "target.bst", element)

    # Test fetch of target with a cached and a non-cached source
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_success()
