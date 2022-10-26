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
import shutil
import pytest

from buildstream import _yaml
from buildstream._testing import cli  # pylint: disable=unused-import

from tests.testutils import create_artifact_share, assert_shared, assert_not_shared


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "junctions",
)


def project_set_artifacts(project, url):
    project_conf_file = os.path.join(project, "project.conf")
    project_config = _yaml.load(project_conf_file, shortname=None)
    project_config["artifacts"] = [{"url": url, "push": True}]
    _yaml.roundtrip_dump(project_config.strip_node_info(), file=project_conf_file)


@pytest.mark.datafiles(DATA_DIR)
def test_push_pull(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "parent")
    base_project = os.path.join(str(project), "base")

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare-parent")) as share, create_artifact_share(
        os.path.join(str(tmpdir), "artifactshare-base")
    ) as base_share:

        # First build it without the artifact cache configured
        result = cli.run(project=project, args=["build", "target.bst"])
        assert result.exit_code == 0

        # Assert that we are now cached locally
        state = cli.get_element_state(project, "target.bst")
        assert state == "cached"
        state = cli.get_element_state(base_project, "base-element.bst")
        assert state == "cached"

        project_set_artifacts(project, share.repo)
        project_set_artifacts(base_project, base_share.repo)

        # Now try bst artifact push
        result = cli.run(project=project, args=["artifact", "push", "--deps", "all", "target.bst"])
        assert result.exit_code == 0

        # And finally assert that the artifacts are in the right shares
        #
        # In the parent project's cache
        assert_shared(cli, share, project, "target.bst", project_name="parent")
        assert_shared(cli, share, project, "app.bst", project_name="parent")
        assert_not_shared(cli, share, base_project, "base-element.bst", project_name="base")

        # In the junction project's cache
        assert_not_shared(cli, base_share, project, "target.bst", project_name="parent")
        assert_not_shared(cli, base_share, project, "app.bst", project_name="parent")
        assert_shared(cli, base_share, base_project, "base-element.bst", project_name="base")

        # Now we've pushed, delete the user's local artifact cache
        # directory and try to redownload it from the share
        #
        cas = os.path.join(cli.directory, "cas")
        shutil.rmtree(cas)
        artifact_dir = os.path.join(cli.directory, "artifacts")
        shutil.rmtree(artifact_dir)

        # Assert that nothing is cached locally anymore
        state = cli.get_element_state(project, "target.bst")
        assert state != "cached"
        state = cli.get_element_state(base_project, "base-element.bst")
        assert state != "cached"

        # Now try bst artifact pull
        result = cli.run(project=project, args=["artifact", "pull", "--deps", "all", "target.bst"])
        assert result.exit_code == 0

        # And assert that they are again in the local cache, without having built
        state = cli.get_element_state(project, "target.bst")
        assert state == "cached"
        state = cli.get_element_state(base_project, "base-element.bst")
        assert state == "cached"
