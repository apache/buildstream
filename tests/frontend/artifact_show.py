#
#  Copyright (C) 2019 Codethink Limited
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
import pytest

from buildstream.exceptions import ErrorDomain
from buildstream.testing import cli  # pylint: disable=unused-import
from tests.testutils import create_artifact_share


# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project",)


# Test artifact show
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_show_element_name(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = "target.bst"

    result = cli.run(project=project, args=["artifact", "show", element])
    result.assert_success()
    assert "not cached {}".format(element) in result.output

    result = cli.run(project=project, args=["build", element])
    result.assert_success()

    result = cli.run(project=project, args=["artifact", "show", element])
    result.assert_success()
    assert "cached {}".format(element) in result.output


# Test artifact show on a failed element
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_show_failed_element(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = "manual.bst"

    result = cli.run(project=project, args=["artifact", "show", element])
    result.assert_success()
    assert "not cached {}".format(element) in result.output

    result = cli.run(project=project, args=["build", element])
    result.assert_task_error(ErrorDomain.SANDBOX, "missing-command")

    result = cli.run(project=project, args=["artifact", "show", element])
    result.assert_success()
    assert "failed {}".format(element) in result.output


# Test artifact show with a deleted dependency
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_show_element_missing_deps(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = "target.bst"
    dependency = "import-bin.bst"

    result = cli.run(project=project, args=["build", element])
    result.assert_success()

    result = cli.run(project=project, args=["artifact", "delete", dependency])
    result.assert_success()

    result = cli.run(project=project, args=["artifact", "show", "--deps", "all", element])
    result.assert_success()
    assert "not cached {}".format(dependency) in result.output
    assert "cached {}".format(element) in result.output


# Test artifact show with artifact ref
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_show_artifact_ref(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = "target.bst"

    result = cli.run(project=project, args=["build", element])
    result.assert_success()

    cache_key = cli.get_element_key(project, element)
    artifact_ref = "test/target/" + cache_key

    result = cli.run(project=project, args=["artifact", "show", artifact_ref])
    result.assert_success()
    assert "cached {}".format(artifact_ref) in result.output


# Test artifact show artifact in remote
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_show_element_available_remotely(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = "target.bst"

    # Set up remote and local shares
    local_cache = os.path.join(str(tmpdir), "artifacts")
    with create_artifact_share(os.path.join(str(tmpdir), "remote")) as remote:
        cli.configure(
            {"artifacts": {"url": remote.repo, "push": True}, "cachedir": local_cache,}
        )

        # Build the element
        result = cli.run(project=project, args=["build", element])
        result.assert_success()

        # Make sure it's in the share
        assert remote.get_artifact(cli.get_artifact_name(project, "test", element))

        # Delete the artifact from the local cache
        result = cli.run(project=project, args=["artifact", "delete", element])
        result.assert_success()
        assert cli.get_element_state(project, element) != "cached"

        result = cli.run(project=project, args=["artifact", "show", element])
        result.assert_success()
        assert "available {}".format(element) in result.output
