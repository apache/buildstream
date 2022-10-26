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

from buildstream._testing import cli_remote_execution as cli  # pylint: disable=unused-import

from tests.testutils import create_artifact_share
from tests.testutils.site import pip_sample_packages  # pylint: disable=unused-import
from tests.testutils.site import SAMPLE_PACKAGES_SKIP_REASON

pytestmark = pytest.mark.remoteexecution

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif("not pip_sample_packages()", reason=SAMPLE_PACKAGES_SKIP_REASON)
def test_buildtree_remote(cli, tmpdir, datafiles):
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"
    share_path = os.path.join(str(tmpdir), "share")

    services = cli.ensure_services()
    assert set(services) == set(["action-cache", "execution", "storage"])

    with create_artifact_share(share_path) as share:
        cli.configure(
            {"artifacts": {"servers": [{"url": share.repo, "push": True}]}, "cache": {"pull-buildtrees": False}}
        )

        res = cli.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
        res.assert_success()

        # remove local cache
        shutil.rmtree(os.path.join(str(tmpdir), "cache", "cas"))
        shutil.rmtree(os.path.join(str(tmpdir), "cache", "artifacts"))

        # pull without buildtree
        res = cli.run(project=project, args=["artifact", "pull", "--deps", "all", element_name])
        res.assert_success()

        # check shell doesn't work
        res = cli.run(project=project, args=["shell", "--build", element_name, "--", "cat", "test"])
        res.assert_shell_error()

        # pull with buildtree
        res = cli.run(project=project, args=["--pull-buildtrees", "artifact", "pull", "--deps", "all", element_name])
        res.assert_success()

        # check it works this time
        res = cli.run(project=project, args=["shell", "--build", element_name, "--use-buildtree", "--", "cat", "test"])
        res.assert_success()
        assert "Hi" in res.output
