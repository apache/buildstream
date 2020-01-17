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

from buildstream.element import _get_normal_name
from buildstream.exceptions import ErrorDomain
from buildstream.testing import cli  # pylint: disable=unused-import
from tests.testutils import create_artifact_share


# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project",)


# Test that we can delete the artifact of the element which corresponds
# to the current project state
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_delete_element(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = "target.bst"

    # Build the element and ensure it's cached
    result = cli.run(project=project, args=["build", element])
    result.assert_success()
    assert cli.get_element_state(project, element) == "cached"

    result = cli.run(project=project, args=["artifact", "delete", element])
    result.assert_success()
    assert cli.get_element_state(project, element) != "cached"


# Test that we can delete an artifact by specifying its ref.
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_delete_artifact(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = "target.bst"

    # Configure a local cache
    local_cache = os.path.join(str(tmpdir), "cache")
    cli.configure({"cachedir": local_cache})

    # First build an element so that we can find its artifact
    result = cli.run(project=project, args=["build", element])
    result.assert_success()

    # Obtain the artifact ref
    cache_key = cli.get_element_key(project, element)
    artifact = os.path.join("test", os.path.splitext(element)[0], cache_key)

    # Explicitly check that the ARTIFACT exists in the cache
    assert os.path.exists(os.path.join(local_cache, "artifacts", "refs", artifact))

    # Delete the artifact
    result = cli.run(project=project, args=["artifact", "delete", artifact])
    result.assert_success()

    # Check that the ARTIFACT is no longer in the cache
    assert not os.path.exists(os.path.join(local_cache, "cas", "refs", "heads", artifact))


# Test the `bst artifact delete` command with multiple, different arguments.
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_delete_element_and_artifact(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = "target.bst"
    dep = "compose-all.bst"

    # Configure a local cache
    local_cache = os.path.join(str(tmpdir), "cache")
    cli.configure({"cachedir": local_cache})

    # First build an element so that we can find its artifact
    result = cli.run(project=project, args=["build", element])
    result.assert_success()
    assert cli.get_element_states(project, [element, dep], deps="none") == {
        element: "cached",
        dep: "cached",
    }

    # Obtain the artifact ref
    cache_key = cli.get_element_key(project, element)
    artifact = os.path.join("test", os.path.splitext(element)[0], cache_key)

    # Explicitly check that the ARTIFACT exists in the cache
    assert os.path.exists(os.path.join(local_cache, "artifacts", "refs", artifact))

    # Delete the artifact
    result = cli.run(project=project, args=["artifact", "delete", artifact, dep])
    result.assert_success()

    # Check that the ARTIFACT is no longer in the cache
    assert not os.path.exists(os.path.join(local_cache, "artifacts", artifact))

    # Check that the dependency ELEMENT is no longer cached
    assert cli.get_element_state(project, dep) != "cached"


# Test that we receive the appropriate stderr when we try to delete an artifact
# that is not present in the cache.
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_delete_unbuilt_artifact(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = "target.bst"

    # delete it, just in case it's there
    _ = cli.run(project=project, args=["artifact", "delete", element])

    # Ensure the element is not cached
    assert cli.get_element_state(project, element) != "cached"

    # Now try and remove it again (now we know its not there)
    result = cli.run(project=project, args=["artifact", "delete", element])

    cache_key = cli.get_element_key(project, element)
    artifact = os.path.join("test", os.path.splitext(element)[0], cache_key)
    expected_err = "WARNING Could not find ref '{}'".format(artifact)
    assert expected_err in result.stderr


# Test that an artifact pulled from it's remote cache (without it's buildtree) will not
# throw an Exception when trying to prune the cache.
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_delete_pulled_artifact_without_buildtree(cli, tmpdir, datafiles):
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

        # Delete and then pull the artifact (without its buildtree)
        result = cli.run(project=project, args=["artifact", "delete", element])
        result.assert_success()
        assert cli.get_element_state(project, element) != "cached"
        result = cli.run(project=project, args=["artifact", "pull", element])
        result.assert_success()
        assert cli.get_element_state(project, element) == "cached"

        # Now delete it again (it should have been pulled without the buildtree, but
        # a digest of the buildtree is pointed to in the artifact's metadata
        result = cli.run(project=project, args=["artifact", "delete", element])
        result.assert_success()
        assert cli.get_element_state(project, element) != "cached"


# Test that we can delete the build deps of an element
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_delete_elements_build_deps(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = "target.bst"

    # Build the element and ensure it's cached
    result = cli.run(project=project, args=["build", element])
    result.assert_success()

    # Assert element and build deps are cached
    assert cli.get_element_state(project, element) == "cached"
    bdep_states = cli.get_element_states(project, [element], deps="build")
    for state in bdep_states.values():
        assert state == "cached"

    result = cli.run(project=project, args=["artifact", "delete", "--deps", "build", element])
    result.assert_success()

    # Assert that the build deps have been deleted and that the artifact remains cached
    assert cli.get_element_state(project, element) == "cached"
    bdep_states = cli.get_element_states(project, [element], deps="build")
    for state in bdep_states.values():
        assert state != "cached"


# Test that we can delete the build deps of an artifact by providing an artifact ref
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_delete_artifacts_build_deps(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = "target.bst"

    # Configure a local cache
    local_cache = os.path.join(str(tmpdir), "cache")
    cli.configure({"cachedir": local_cache})

    # First build an element so that we can find its artifact
    result = cli.run(project=project, args=["build", element])
    result.assert_success()

    # Obtain the artifact ref
    cache_key = cli.get_element_key(project, element)
    artifact = os.path.join("test", os.path.splitext(element)[0], cache_key)

    # Explicitly check that the ARTIFACT exists in the cache
    assert os.path.exists(os.path.join(local_cache, "artifacts", "refs", artifact))

    # get the artifact refs of the build dependencies
    bdep_refs = []
    bdep_states = cli.get_element_states(project, [element], deps="build")
    for bdep in bdep_states.keys():
        bdep_refs.append(os.path.join("test", _get_normal_name(bdep), cli.get_element_key(project, bdep)))

    # Assert build dependencies are cached
    for ref in bdep_refs:
        assert os.path.exists(os.path.join(local_cache, "artifacts", "refs", ref))

    # Delete the artifact
    result = cli.run(project=project, args=["artifact", "delete", "--deps", "build", artifact])
    result.assert_success()

    # Check that the artifact's build deps are no longer in the cache
    # Assert build dependencies have been deleted and that the artifact remains
    for ref in bdep_refs:
        assert not os.path.exists(os.path.join(local_cache, "artifacts", "refs", ref))
    assert os.path.exists(os.path.join(local_cache, "artifacts", "refs", artifact))


# Test that `--deps all` option fails if an artifact ref is specified
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_delete_artifact_with_deps_all_fails(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = "target.bst"

    # First build an element so that we can find its artifact
    result = cli.run(project=project, args=["build", element])
    result.assert_success()

    # Obtain the artifact ref
    cache_key = cli.get_element_key(project, element)
    artifact = os.path.join("test", os.path.splitext(element)[0], cache_key)

    # Try to delete the artifact with all of its dependencies
    result = cli.run(project=project, args=["artifact", "delete", "--deps", "all", artifact])
    result.assert_main_error(ErrorDomain.STREAM, None)

    assert "Error: '--deps all' is not supported for artifact refs" in result.stderr
