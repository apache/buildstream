#  Copyright (C) 2019 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import shutil
import pytest

from buildstream.testing import cli_remote_execution as cli  # pylint: disable=unused-import

from tests.testutils import create_artifact_share

pytestmark = pytest.mark.remoteexecution

# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project",)


@pytest.mark.datafiles(DATA_DIR)
def test_buildtree_remote(cli, tmpdir, datafiles):
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"
    share_path = os.path.join(str(tmpdir), "share")

    services = cli.ensure_services()
    assert set(services) == set(["action-cache", "execution", "storage"])

    with create_artifact_share(share_path) as share:
        cli.configure({"artifacts": {"url": share.repo, "push": True}, "cache": {"pull-buildtrees": False}})

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
        res = cli.run(
            project=project, args=["shell", "--build", element_name, "--use-buildtree", "always", "--", "cat", "test"]
        )
        res.assert_success()
        assert "Hi" in res.output
