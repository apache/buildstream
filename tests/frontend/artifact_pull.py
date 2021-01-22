# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import shutil

import pytest

from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream.exceptions import ErrorDomain

from tests.testutils import create_artifact_share


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")

#
# Test modes of `bst artifact pull` when given an artifact
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "deps,expect_cached",
    [
        # When pulling an artifact with --deps none, we expect that artifact to be pulled
        ("none", ["target.bst"]),
        # When pulling an artifact with --deps build, we expect the build deps to be pulled
        ("build", ["import-bin.bst", "compose-all.bst"]),
        # Pulling an artifact with --deps run is not supported without a local project
        ("run", []),
        # Pulling an artifact with --deps all is not supported without a local project
        ("all", []),
    ],
    ids=["none", "build", "run", "all"],
)
def test_pull(cli, tmpdir, datafiles, deps, expect_cached):
    project = str(datafiles)

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:
        # Build the element to push it to cache
        cli.configure({"artifacts": {"url": share.repo, "push": True}})

        # Build it
        result = cli.run(project=project, args=["build", "target.bst"])
        result.assert_success()

        # Assert it is cached locally and remotely
        assert cli.get_element_state(project, "target.bst") == "cached"
        assert share.get_artifact(cli.get_artifact_name(project, "test", "target.bst"))

        # Obtain the artifact name for pulling purposes
        artifact_name = cli.get_artifact_name(project, "test", "target.bst")

        # Discard the local cache
        shutil.rmtree(str(os.path.join(str(tmpdir), "cache", "cas")))
        shutil.rmtree(str(os.path.join(str(tmpdir), "cache", "artifacts")))
        assert cli.get_element_state(project, "target.bst") != "cached"

        # Now run our pull test
        result = cli.run(project=project, args=["artifact", "pull", "--deps", deps, artifact_name])

        if deps in ["all", "run"]:
            result.assert_main_error(ErrorDomain.STREAM, "deps-not-supported")
        else:
            result.assert_success()

        # After pulling, assert that we have the expected elements cached again.
        states = cli.get_element_states(project, ["target.bst"])
        for expect in expect_cached:
            assert states[expect] == "cached"
