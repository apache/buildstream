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
# Test modes of `bst artifact checkout --pull` when given an artifact name
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "deps,expect_exist,expect_noexist",
    [
        # Deps none: We only expect the file from target-import.bst
        ("none", ["foo"], ["usr/bin/hello", "usr/include/pony.h"]),
        # Deps build: We only expect the files from the build dependencies
        ("build", ["usr/bin/hello", "usr/include/pony.h"], ["foo"]),
        # Deps run: not supported without a local project
        ("run", [], []),
        # Deps all: not supported without a local project
        ("all", [], []),
    ],
    ids=["none", "build", "run", "all"],
)
def test_checkout(cli, tmpdir, datafiles, deps, expect_exist, expect_noexist):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:
        # Build the element to push it to cache
        cli.configure({"artifacts": {"url": share.repo, "push": True}})

        # Build it
        result = cli.run(project=project, args=["build", "target-import.bst"])
        result.assert_success()

        # Assert it is cached locally and remotely
        assert cli.get_element_state(project, "target-import.bst") == "cached"
        assert share.get_artifact(cli.get_artifact_name(project, "test", "target-import.bst"))

        # Obtain the artifact name for pulling purposes
        artifact_name = cli.get_artifact_name(project, "test", "target-import.bst")

        # Discard the local cache
        shutil.rmtree(str(os.path.join(str(tmpdir), "cache", "cas")))
        shutil.rmtree(str(os.path.join(str(tmpdir), "cache", "artifacts")))
        assert cli.get_element_state(project, "target-import.bst") != "cached"

        # Now checkout the artifacy
        result = cli.run(
            project=project,
            args=["artifact", "checkout", "--directory", checkout, "--pull", "--deps", deps, artifact_name],
        )

        if deps in ["all", "run"]:
            result.assert_main_error(ErrorDomain.STREAM, "deps-not-supported")
        else:
            result.assert_success()

        # After checkout, assert that we have the expected files and assert that
        # we don't have any of the unexpected files.
        #
        for expect in expect_exist:
            filename = os.path.join(checkout, expect)
            assert os.path.exists(filename)

        for expect in expect_noexist:
            filename = os.path.join(checkout, expect)
            assert not os.path.exists(filename)
