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
#  Authors:
#        Raoul Hidalgo Charman <raoul.hidalgocharman@codethink.co.uk>
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import shutil

import pytest

from buildstream.testing.runcli import cli  # pylint: disable=unused-import

from tests.testutils.artifactshare import create_artifact_share
from tests.testutils.element_generators import create_element_size


DATA_DIR = os.path.dirname(os.path.realpath(__file__))


# Test that when we have sources only in the local CAS buildstream fetches them
# for opening a workspace
@pytest.mark.datafiles(DATA_DIR)
def test_workspace_source_fetch(tmpdir, datafiles, cli):
    project_dir = os.path.join(str(tmpdir), "project")
    element_path = "elements"
    source_dir = os.path.join(str(tmpdir), "cache", "sources")
    workspace = os.path.join(cli.directory, "workspace")

    cli.configure({"cachedir": os.path.join(str(tmpdir), "cache")})

    create_element_size("target.bst", project_dir, element_path, [], 10000)
    res = cli.run(project=project_dir, args=["build", "target.bst"])
    res.assert_success()
    assert "Fetching from" in res.stderr

    # remove the original sources
    shutil.rmtree(source_dir)

    # Open a workspace and check that fetches the original sources
    res = cli.run(project=project_dir, args=["workspace", "open", "target.bst", "--directory", workspace])
    res.assert_success()
    assert "Fetching from" in res.stderr

    assert os.listdir(workspace) != []


@pytest.mark.datafiles(DATA_DIR)
def test_workspace_open_no_source_push(tmpdir, datafiles, cli):
    project_dir = os.path.join(str(tmpdir), "project")
    element_path = "elements"
    cache_dir = os.path.join(str(tmpdir), "cache")
    share_dir = os.path.join(str(tmpdir), "share")
    workspace = os.path.join(cli.directory, "workspace")

    with create_artifact_share(share_dir) as share:
        cli.configure(
            {"cachedir": cache_dir, "scheduler": {"pushers": 1}, "source-caches": {"url": share.repo, "push": True,},}
        )

        # Fetch as in previous test and check it pushes the source
        create_element_size("target.bst", project_dir, element_path, [], 10000)
        res = cli.run(project=project_dir, args=["build", "target.bst"])
        res.assert_success()
        assert "Fetching from" in res.stderr
        assert "Pushed source" in res.stderr

        # clear the cas and open a workspace
        shutil.rmtree(os.path.join(cache_dir, "cas"))
        res = cli.run(project=project_dir, args=["workspace", "open", "target.bst", "--directory", workspace])
        res.assert_success()

        # Check that this time it does not push the sources
        res = cli.run(project=project_dir, args=["build", "target.bst"])
        res.assert_success()
        assert "Pushed source" not in res.stderr
