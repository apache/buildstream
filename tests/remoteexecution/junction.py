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

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest
from buildstream.testing import cli_remote_execution as cli  # pylint: disable=unused-import
from buildstream.testing import create_repo
from buildstream import _yaml
from tests.testutils import generate_junction

pytestmark = pytest.mark.remoteexecution

# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project",)


def configure_project(path, config):
    config["name"] = "test"
    config["element-path"] = "elements"
    _yaml.roundtrip_dump(config, os.path.join(path, "project.conf"))


def create_element(repo, name, path, dependencies, ref=None):
    element = {"kind": "import", "sources": [repo.source_config(ref=ref)], "depends": dependencies}
    _yaml.roundtrip_dump(element, os.path.join(path, name))


@pytest.mark.datafiles(DATA_DIR)
def test_junction_build_remote(cli, tmpdir, datafiles):
    project = str(datafiles)
    subproject_path = os.path.join(project, "files", "sub-project")
    subproject_element_path = os.path.join(subproject_path, "elements")
    amhello_files_path = os.path.join(subproject_path, "files")
    element_path = os.path.join(project, "elements")
    junction_path = os.path.join(element_path, "junction.bst")

    # We need a repo for real trackable elements
    repo = create_repo("git", str(tmpdir))
    ref = repo.create(amhello_files_path)

    # ensure that the correct project directory is also listed in the junction
    subproject_conf = os.path.join(subproject_path, "project.conf")
    with open(subproject_conf) as f:
        config = f.read()
    config = config.format(project_dir=subproject_path)
    with open(subproject_conf, "w") as f:
        f.write(config)

    # Create a trackable element to depend on the cross junction element,
    # this one has it's ref resolved already
    create_element(repo, "sub-target.bst", subproject_element_path, ["autotools/amhello.bst"], ref=ref)

    # Create a trackable element to depend on the cross junction element
    create_element(repo, "target.bst", element_path, [{"junction": "junction.bst", "filename": "sub-target.bst"}])

    # Create a repo to hold the subproject and generate a junction element for it
    generate_junction(tmpdir, subproject_path, junction_path, store_ref=False)

    # Now create a compose element at the top level
    element = {"kind": "compose", "depends": [{"filename": "target.bst", "type": "build"}]}
    _yaml.roundtrip_dump(element, os.path.join(element_path, "composed.bst"))

    # We're doing remote execution so ensure services are available
    services = cli.ensure_services()
    assert set(services) == set(["action-cache", "execution", "storage"])

    # track the junction first to ensure we have refs
    result = cli.run(project=project, args=["source", "track", "junction.bst"])
    result.assert_success()

    # track target to ensure we have refs
    result = cli.run(project=project, args=["source", "track", "--deps", "all", "composed.bst"])
    result.assert_success()

    # build
    result = cli.run(project=project, silent=True, args=["build", "composed.bst"])
    result.assert_success()

    # Assert that the main target is cached as a result
    assert cli.get_element_state(project, "composed.bst") == "cached"
