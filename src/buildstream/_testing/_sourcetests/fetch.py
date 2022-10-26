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
from .._utils import generate_junction
from .. import create_repo
from .. import cli  # pylint: disable=unused-import
from .utils import update_project_configuration
from .utils import kind  # pylint: disable=unused-import


# Project directory
TOP_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TOP_DIR, "project")


@pytest.mark.datafiles(DATA_DIR)
def test_fetch(cli, tmpdir, datafiles, kind):
    project = str(datafiles)
    bin_files_path = os.path.join(project, "files", "bin-files")
    element_path = os.path.join(project, "elements")
    element_name = "fetch-test-{}.bst".format(kind)

    # Create our repo object of the given source type with
    # the bin files, and then collect the initial ref.
    #
    repo = create_repo(kind, str(tmpdir))
    ref = repo.create(bin_files_path)

    # Write out our test target
    element = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

    # Assert that a fetch is needed
    assert cli.get_element_state(project, element_name) == "fetch needed"

    # Now try to fetch it
    result = cli.run(project=project, args=["source", "fetch", element_name])
    result.assert_success()

    # Assert that we are now buildable because the source is
    # now cached.
    assert cli.get_element_state(project, element_name) == "buildable"


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", ["inline", "project.refs"])
def test_fetch_cross_junction(cli, tmpdir, datafiles, ref_storage, kind):
    project = str(datafiles)
    subproject_path = os.path.join(project, "files", "sub-project")
    junction_path = os.path.join(project, "elements", "junction.bst")

    import_etc_path = os.path.join(subproject_path, "elements", "import-etc-repo.bst")
    etc_files_path = os.path.join(subproject_path, "files", "etc-files")

    repo = create_repo(kind, str(tmpdir.join("import-etc")))
    ref = repo.create(etc_files_path)

    element = {"kind": "import", "sources": [repo.source_config(ref=(ref if ref_storage == "inline" else None))]}
    _yaml.roundtrip_dump(element, import_etc_path)

    update_project_configuration(project, {"ref-storage": ref_storage})

    generate_junction(tmpdir, subproject_path, junction_path, store_ref=(ref_storage == "inline"))

    if ref_storage == "project.refs":
        result = cli.run(project=project, args=["source", "track", "junction.bst"])
        result.assert_success()
        result = cli.run(project=project, args=["source", "track", "junction.bst:import-etc.bst"])
        result.assert_success()

    result = cli.run(project=project, args=["source", "fetch", "junction.bst:import-etc.bst"])
    result.assert_success()
