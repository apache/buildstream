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

from buildstream._testing import cli  # pylint: disable=unused-import
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
@pytest.mark.parametrize("with_project", [True, False], ids=["with-project", "without-project"])
def test_checkout(cli, tmpdir, datafiles, deps, expect_exist, expect_noexist, with_project):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:
        # Build the element to push it to cache
        cli.configure({"artifacts": {"servers": [{"url": share.repo, "push": True}]}})

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

        # Delete the project.conf if we're going to try this without a project
        if not with_project:
            os.remove(os.path.join(project, "project.conf"))

        # Now checkout the artifact
        result = cli.run(
            project=project,
            args=["artifact", "checkout", "--directory", checkout, "--deps", deps, artifact_name],
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
