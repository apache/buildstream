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
#  Authors: Richard Maw <richard.maw@codethink.co.uk>
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import shutil

import pytest

from buildstream._testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream._testing._utils.site import HAVE_SANDBOX

from tests.testutils import create_artifact_share


pytestmark = pytest.mark.integration


# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


# A test to capture the integration of the cachebuildtrees
# behaviour, which by default is to include the buildtree
# content of an element on caching.

# Dse this really need a sandbox?
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_cache_buildtrees(cli, tmpdir, datafiles):
    project = str(datafiles)
    element_name = "autotools/amhello.bst"
    cwd = str(tmpdir)

    # Create artifact shares for pull & push testing
    with create_artifact_share(os.path.join(str(tmpdir), "share1")) as share1, create_artifact_share(
        os.path.join(str(tmpdir), "share2")
    ) as share2, create_artifact_share(os.path.join(str(tmpdir), "share3")) as share3:
        cli.configure({"artifacts": {"servers": [{"url": share1.repo, "push": True}]}, "cachedir": str(tmpdir)})

        # Build autotools element with the default behavior of caching buildtrees
        # only when necessary. The artifact should be successfully pushed to the share1 remote
        # and cached locally with an 'empty' buildtree digest, as it's not a
        # dangling ref
        result = cli.run(project=project, args=["build", element_name])
        assert result.exit_code == 0
        assert cli.get_element_state(project, element_name) == "cached"
        assert share1.get_artifact(cli.get_artifact_name(project, "test", element_name))

        # The buildtree dir should not exist, as we set the config to not cache buildtrees.

        artifact_name = cli.get_artifact_name(project, "test", element_name)
        assert share1.get_artifact(artifact_name)
        with cli.artifact.extract_buildtree(cwd, cwd, artifact_name) as buildtreedir:
            assert not buildtreedir

        # Delete the local cached artifacts, and assert the when pulled with --pull-buildtrees
        # that is was cached in share1 as expected without a buildtree dir
        shutil.rmtree(os.path.join(str(tmpdir), "cas"))
        shutil.rmtree(os.path.join(str(tmpdir), "artifacts"))
        assert cli.get_element_state(project, element_name) != "cached"
        result = cli.run(project=project, args=["--pull-buildtrees", "artifact", "pull", element_name])
        assert element_name in result.get_pulled_elements()
        with cli.artifact.extract_buildtree(cwd, cwd, artifact_name) as buildtreedir:
            assert not buildtreedir
        shutil.rmtree(os.path.join(str(tmpdir), "cas"))
        shutil.rmtree(os.path.join(str(tmpdir), "artifacts"))

        # Assert that the default behaviour of pull to not include buildtrees on the artifact
        # in share1 which was purposely cached with an empty one behaves as expected. As such the
        # pulled artifact will have a dangling ref for the buildtree dir, regardless of content,
        # leading to no buildtreedir being extracted
        result = cli.run(project=project, args=["artifact", "pull", element_name])
        assert element_name in result.get_pulled_elements()
        with cli.artifact.extract_buildtree(cwd, cwd, artifact_name) as buildtreedir:
            assert not buildtreedir
        shutil.rmtree(os.path.join(str(tmpdir), "cas"))
        shutil.rmtree(os.path.join(str(tmpdir), "artifacts"))

        # Repeat building the artifacts, this time with cache-buildtrees set to
        # 'always' via the cli, as such the buildtree dir should not be empty
        cli.configure({"artifacts": {"servers": [{"url": share2.repo, "push": True}]}, "cachedir": str(tmpdir)})
        result = cli.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
        assert result.exit_code == 0
        assert cli.get_element_state(project, element_name) == "cached"
        assert share2.get_artifact(cli.get_artifact_name(project, "test", element_name))

        # Cache key will be the same however the digest hash will have changed as expected, so reconstruct paths
        with cli.artifact.extract_buildtree(cwd, cwd, artifact_name) as buildtreedir:
            assert os.path.isdir(buildtreedir)
            assert os.listdir(buildtreedir)

        # Delete the local cached artifacts, and assert that when pulled with --pull-buildtrees
        # that it was cached in share2 as expected with a populated buildtree dir
        shutil.rmtree(os.path.join(str(tmpdir), "cas"))
        shutil.rmtree(os.path.join(str(tmpdir), "artifacts"))
        assert cli.get_element_state(project, element_name) != "cached"
        result = cli.run(project=project, args=["--pull-buildtrees", "artifact", "pull", element_name])
        assert element_name in result.get_pulled_elements()
        with cli.artifact.extract_buildtree(cwd, cwd, artifact_name) as buildtreedir:
            assert os.path.isdir(buildtreedir)
            assert os.listdir(buildtreedir)
        shutil.rmtree(os.path.join(str(tmpdir), "cas"))
        shutil.rmtree(os.path.join(str(tmpdir), "artifacts"))

        # Clarify that the user config option for cache-buildtrees works as the cli
        # main option does. Point to share3 which does not have the artifacts cached to force
        # a build
        cli.configure(
            {
                "artifacts": {"servers": [{"url": share3.repo, "push": True}]},
                "cachedir": str(tmpdir),
                "cache": {"cache-buildtrees": "always"},
            }
        )
        result = cli.run(project=project, args=["build", element_name])
        assert result.exit_code == 0
        assert cli.get_element_state(project, element_name) == "cached"
        with cli.artifact.extract_buildtree(cwd, cwd, artifact_name) as buildtreedir:
            assert os.path.isdir(buildtreedir)
            assert os.listdir(buildtreedir)


#
# This test asserts that the environment variables are indeed preserved in
# generated artifacts, and asserts that local project state is not erronously
# observed when checking out and integrating an artifact by artifact name.
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_preserve_environment(datafiles, cli):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")

    #
    # First build the target, this will create the echo-env-var.bst artifact
    # and cache an integration command which uses it's build environment
    # to create /etc/test.conf
    #
    result = cli.run(project=project, args=["build", "echo-target.bst"])
    result.assert_success()

    #
    # Now preserve the cache key of the toplevel
    #
    key = cli.get_element_key(project, "echo-target.bst")

    #
    # From here on out, we will augment the project.conf with a modified
    # environment, causing the definition of the element to change and
    # consequently the cache key.
    #
    project_config = {"environment": {"TEST_VAR": "horsy"}}

    #
    # This should changed the cache key such that a different artifact
    # would be produced, as the environment has changed.
    #
    result = cli.run_project_config(
        project=project,
        project_config=project_config,
        args=["show", "--deps", "none", "--format", "%{full-key}", "echo-target.bst"],
    )
    result.assert_success()
    assert result.output.strip() != key

    #
    # Now checkout the originally built artifact and request that it be integrated,
    # this will run integration commands encoded into the artifact.
    #
    checkout_args = [
        "artifact",
        "checkout",
        "--directory",
        checkout,
        "--deps",
        "build",
        "--integrate",
        "test/echo-target/" + key,
    ]
    result = cli.run_project_config(project=project, args=checkout_args, project_config=project_config)
    result.assert_success()

    #
    # Now observe the file generated by echo-env-var.bst's integration command.
    #
    # Here we assert that the actual environment from the artifact is being
    # used to run the integration command, and not the irrelevant project
    # data in the local project directory.
    #
    filename = os.path.join(checkout, "etc", "test.conf")
    assert os.path.exists(filename)
    with open(filename, "r", encoding="utf-8") as f:
        data = f.read()
        data = data.strip()
        assert data == "pony"
