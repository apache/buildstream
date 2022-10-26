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
@pytest.mark.parametrize("with_project", [True, False], ids=["with-project", "without-project"])
def test_pull(cli, tmpdir, datafiles, deps, expect_cached, with_project):
    project = str(datafiles)

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:

        # Build the element to push it to cache, and explicitly configure local cache so we can check it
        local_cache = os.path.join(str(tmpdir), "cache")
        cli.configure({"cachedir": local_cache, "artifacts": {"servers": [{"url": share.repo, "push": True}]}})

        # Build it
        result = cli.run(project=project, args=["build", "target.bst"])
        result.assert_success()

        # Assert it is cached locally and remotely
        assert cli.get_element_state(project, "target.bst") == "cached"
        assert share.get_artifact(cli.get_artifact_name(project, "test", "target.bst"))

        # Obtain the artifact name for pulling purposes
        artifact_name = cli.get_artifact_name(project, "test", "target.bst")

        # Translate the expected element names into artifact names
        expect_cached_artifacts = [
            cli.get_artifact_name(project, "test", element_name) for element_name in expect_cached
        ]

        # Discard the local cache
        shutil.rmtree(str(os.path.join(str(tmpdir), "cache", "cas")))
        shutil.rmtree(str(os.path.join(str(tmpdir), "cache", "artifacts")))
        assert cli.get_element_state(project, "target.bst") != "cached"

        # Delete the project.conf if we're going to try this without a project
        if not with_project:
            os.remove(os.path.join(project, "project.conf"))

        # Now run our pull test
        result = cli.run(project=project, args=["artifact", "pull", "--deps", deps, artifact_name])

        if deps in ["all", "run"]:
            result.assert_main_error(ErrorDomain.STREAM, "deps-not-supported")
        else:
            result.assert_success()

        # After pulling, assert that we have the expected elements cached again.
        #
        # Note that we do not use cli.get_element_states() here because the project.conf
        # might not be present, so we poke at the cache directly for this assertion.
        for expect in expect_cached_artifacts:
            assert os.path.exists(os.path.join(local_cache, "artifacts", "refs", expect))
