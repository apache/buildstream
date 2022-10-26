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

from buildstream import _yaml
from .. import create_repo
from .. import cli  # pylint: disable=unused-import
from .utils import kind  # pylint: disable=unused-import

# Project directory
TOP_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TOP_DIR, "project")


@pytest.mark.datafiles(DATA_DIR)
def test_open(cli, tmpdir_factory, datafiles, kind):
    project_path = str(datafiles)
    bin_files_path = os.path.join(project_path, "files", "bin-files")

    element_name = "workspace-test-{}.bst".format(kind)
    element_path = os.path.join(project_path, "elements")

    # Create our repo object of the given source type with
    # the bin files, and then collect the initial ref.
    repo = create_repo(kind, str(tmpdir_factory.mktemp("repo-{}".format(kind))))
    ref = repo.create(bin_files_path)

    # Write out our test target
    element = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

    # Assert that there is no reference, a fetch is needed
    assert cli.get_element_state(project_path, element_name) == "fetch needed"

    workspace_dir = os.path.join(tmpdir_factory.mktemp("opened_workspace"))

    # Now open the workspace, this should have the effect of automatically
    # fetching the source from the repo.
    result = cli.run(project=project_path, args=["workspace", "open", "--directory", workspace_dir, element_name])

    result.assert_success()

    # Assert that we are now buildable because the source is now cached.
    assert cli.get_element_state(project_path, element_name) == "buildable"

    # Check that the executable hello file is found in each workspace
    filename = os.path.join(workspace_dir, "usr", "bin", "hello")
    assert os.path.exists(filename)
