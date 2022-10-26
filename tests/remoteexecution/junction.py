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
from buildstream._testing import cli_remote_execution as cli  # pylint: disable=unused-import
from buildstream._testing import create_repo
from buildstream import _yaml
from tests.testutils import generate_junction
from tests.testutils.site import pip_sample_packages  # pylint: disable=unused-import
from tests.testutils.site import SAMPLE_PACKAGES_SKIP_REASON

pytestmark = pytest.mark.remoteexecution

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


def configure_project(path, config):
    config["name"] = "test"
    config["element-path"] = "elements"
    _yaml.roundtrip_dump(config, os.path.join(path, "project.conf"))


def create_element(repo, name, path, dependencies, ref=None):
    element = {"kind": "import", "sources": [repo.source_config(ref=ref)], "depends": dependencies}
    _yaml.roundtrip_dump(element, os.path.join(path, name))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif("not pip_sample_packages()", reason=SAMPLE_PACKAGES_SKIP_REASON)
def test_junction_build_remote(cli, tmpdir, datafiles):
    project = str(datafiles)
    subproject_path = os.path.join(project, "files", "sub-project")
    subproject_element_path = os.path.join(subproject_path, "elements")
    amhello_files_path = os.path.join(subproject_path, "files")
    element_path = os.path.join(project, "elements")
    junction_path = os.path.join(element_path, "junction.bst")

    # We need a repo for real trackable elements
    repo = create_repo("tar", str(tmpdir))
    ref = repo.create(amhello_files_path)

    # ensure that the correct project directory is also listed in the junction
    subproject_conf = os.path.join(subproject_path, "project.conf")
    with open(subproject_conf, encoding="utf-8") as f:
        config = f.read()
    config = config.format(project_dir=subproject_path)
    with open(subproject_conf, "w", encoding="utf-8") as f:
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
