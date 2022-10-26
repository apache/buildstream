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

from buildstream._testing import cli, cli_integration, Cli  # pylint: disable=unused-import
from buildstream.exceptions import ErrorDomain
from buildstream._testing._utils.site import HAVE_SANDBOX

from tests.testutils import ArtifactShare


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


#
# Ensure that we didn't get a build tree if we didn't ask for one
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_buildtree_unused(cli_integration, datafiles):
    # We can only test the non interacitve case
    # The non interactive case defaults to not using buildtrees
    # for `bst shell --build`
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"

    res = cli_integration.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
    res.assert_success()

    res = cli_integration.run(project=project, args=["shell", "--build", element_name, "--", "cat", "test"])
    res.assert_shell_error()


#
# Ensure we can use a buildtree from a successful build
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_buildtree_from_success(cli_integration, datafiles):
    # Test that if we ask for a build tree it is there.
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"

    res = cli_integration.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
    res.assert_success()

    res = cli_integration.run(
        project=project, args=["shell", "--build", "--use-buildtree", element_name, "--", "cat", "test"]
    )
    res.assert_success()
    assert "Hi" in res.output


#
# Ensure we can use a buildtree from a failed build
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_buildtree_from_failure(cli_integration, datafiles):
    # Test that we can use a build tree after a failure
    project = str(datafiles)
    element_name = "build-shell/buildtree-fail.bst"

    res = cli_integration.run(project=project, args=["build", element_name])
    res.assert_main_error(ErrorDomain.STREAM, None)

    # Assert that file has expected contents
    res = cli_integration.run(
        project=project, args=["shell", "--build", element_name, "--use-buildtree", "--", "cat", "test"]
    )
    res.assert_success()
    assert "WARNING using a buildtree from a failed build" in res.stderr
    assert "Hi" in res.output


###########################################################################
#                        Custom fixture ahead                             #
###########################################################################
#
# There are a lot of scenarios to test with launching shells with various states
# of local cache, which all require that artifacts be built in an artifact share.
#
# We want to use @pytest.mark.parametrize() here so that we can more coherently test
# specific scenarios, but testing each of these in a separate test is very expensive.
#
# For this reason, we use some module scope fixtures which will prepare the
# ArtifactShare() object by building and pushing to it, and the same ArtifactShare()
# object is shared across all tests which need the ArtifactShare() to be in that
# given state.
#
# This means we only need to download (fetch) the external alpine runtime and
# push it to our internal ArtifactShare() once, but we can reuse it for many
# parametrized tests.
#
# It is important that none of the tests using these fixtures access the
# module scope ArtifactShare() instances with "push" access, as tests
# should not be modifying the state of the shared data.
#
###########################################################################


# create_built_artifact_share()
#
# A helper function to create an ArtifactShare object with artifacts
# prebuilt, this can be shared across multiple tests which access
# the artifact share in a read-only fashion.
#
# Args:
#    tmpdir (str): The temp directory to be used
#    cache_buildtrees (bool): Whether to cache buildtrees when building
#    integration_cache (IntegrationCache): The session wide integration cache so that we
#                                          can reuse the sources from previous runs
#
def create_built_artifact_share(tmpdir, cache_buildtrees, integration_cache):
    element_name = "build-shell/buildtree.bst"

    # Replicate datafiles behavior and do work entirely in the temp directory
    project = os.path.join(tmpdir, "project")
    shutil.copytree(DATA_DIR, project)

    # Create the share to be hosted from this temp directory
    share = ArtifactShare(os.path.join(tmpdir, "artifactcache"))

    # Create a Cli instance to build and populate the share
    cli = Cli(os.path.join(tmpdir, "cache"))
    cli.configure(
        {"artifacts": {"servers": [{"url": share.repo, "push": True}]}, "sourcedir": integration_cache.sources}
    )

    # Optionally cache build trees
    args = []
    if cache_buildtrees:
        args += ["--cache-buildtrees", "always"]
    args += ["build", element_name]

    # Build
    result = cli.run(project=project, args=args)
    result.assert_success()

    # Assert that the artifact is indeed in the share
    assert cli.get_element_state(project, element_name) == "cached"
    artifact_name = cli.get_artifact_name(project, "test", element_name)
    assert share.get_artifact(artifact_name)

    return share


# share_with_buildtrees()
#
# A module scope fixture which prepares an ArtifactShare() instance
# which will have all dependencies of "build-shell/buildtree.bst" built and
# cached with buildtrees also cached.
#
@pytest.fixture(scope="module")
def share_with_buildtrees(tmp_path_factory, integration_cache):
    # Get a temporary directory for this module scope fixture
    tmpdir = tmp_path_factory.mktemp("artifact_share_with_buildtrees")

    # Create our ArtifactShare instance which will persist for the duration of
    # the class scope fixture.
    share = create_built_artifact_share(tmpdir, True, integration_cache)
    try:
        yield share
    finally:
        share.close()


# share_without_buildtrees()
#
# A module scope fixture which prepares an ArtifactShare() instance
# which will have all dependencies of "build-shell/buildtree.bst" built
# but without caching any buildtrees.
#
@pytest.fixture(scope="module")
def share_without_buildtrees(tmp_path_factory, integration_cache):
    # Get a temporary directory for this module scope fixture
    tmpdir = tmp_path_factory.mktemp("artifact_share_without_buildtrees")

    # Create our ArtifactShare instance which will persist for the duration of
    # the class scope fixture.
    share = create_built_artifact_share(tmpdir, False, integration_cache)
    try:
        yield share
    finally:
        share.close()


# maybe_pull_deps()
#
# Convenience function for optionally pulling element dependencies
# in the following parametrized tests.
#
# Args:
#    cli (Cli): The Cli object
#    project (str): The project path
#    element_name (str): The element name
#    pull_deps (str): The argument for `--deps`, or None
#    pull_buildtree (bool): Whether to also pull buildtrees
#
def maybe_pull_deps(cli, project, element_name, pull_deps, pull_buildtree):

    # Optionally pull the buildtree along with `bst artifact pull`
    if pull_deps:
        args = []
        if pull_buildtree:
            args += ["--pull-buildtrees"]
        args += ["artifact", "pull", "--deps", pull_deps, element_name]

        # Pull from cache
        result = cli.run(project=project, args=args)
        result.assert_success()


#
# Test behavior of launching a shell and requesting to use a buildtree, with
# various states of local cache (ranging from nothing cached to everything cached)
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.parametrize(
    "pull_deps,pull_buildtree,expect_error",
    [
        # Don't pull at all
        (None, False, "missing-buildtree-artifact-not-cached"),
        # Pull only dependencies
        ("build", False, "missing-buildtree-artifact-not-cached"),
        # Pull all elements including the shell element, but without the buildtree
        ("all", False, "missing-buildtree-artifact-buildtree-not-cached"),
        # Pull all elements including the shell element, and pull buildtrees
        ("all", True, None),
        # Pull only the artifact, but without the buildtree
        ("none", False, "missing-buildtree-artifact-buildtree-not-cached"),
        # Pull only the artifact with its buildtree
        ("none", True, None),
    ],
    ids=[
        "no-pull",
        "pull-only-deps",
        "pull-without-buildtree",
        "pull-with-buildtree",
        "pull-target-without-buildtree",
        "pull-target-with-buildtree",
    ],
)
def test_shell_use_cached_buildtree(share_with_buildtrees, datafiles, cli, pull_deps, pull_buildtree, expect_error):
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"

    cli.configure({"artifacts": {"servers": [{"url": share_with_buildtrees.repo}]}})

    # Optionally pull the buildtree along with `bst artifact pull`
    maybe_pull_deps(cli, project, element_name, pull_deps, pull_buildtree)

    # Disable access to the artifact server after pulling, so that `bst shell` cannot automatically
    # pull the missing bits, this should be equivalent to the missing bits being missing in a
    # remote server
    cli.configure({"artifacts": {}})

    # Run the shell without asking it to pull any buildtree, just asking to use a buildtree
    result = cli.run(project=project, args=["shell", "--build", element_name, "--use-buildtree", "--", "cat", "test"])

    if expect_error:
        result.assert_main_error(ErrorDomain.APP, expect_error)
    else:
        result.assert_success()
        assert "Hi" in result.output


#
# Test behavior of launching a shell and requesting to use a buildtree, while allowing
# BuildStream to download any missing bits from the artifact server on the fly (which
# it will do by default) again with various states of local cache (ranging from nothing
# cached to everything cached)
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.parametrize(
    "pull_deps,pull_buildtree",
    [
        # Don't pull at all
        (None, False),
        # Pull only dependencies
        ("build", False),
        # Pull all elements including the shell element, but without the buildtree
        ("all", False),
        # Pull all elements including the shell element, and pull buildtrees
        ("all", True),
    ],
    ids=["no-pull", "pull-only-deps", "pull-without-buildtree", "pull-with-buildtree"],
)
def test_shell_pull_cached_buildtree(share_with_buildtrees, datafiles, cli, pull_deps, pull_buildtree):
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"

    cli.configure({"artifacts": {"servers": [{"url": share_with_buildtrees.repo}]}})

    # Optionally pull the buildtree along with `bst artifact pull`
    maybe_pull_deps(cli, project, element_name, pull_deps, pull_buildtree)

    # Run the shell and request that required artifacts and buildtrees should be pulled
    result = cli.run(
        project=project,
        args=[
            "--pull-buildtrees",
            "shell",
            "--build",
            element_name,
            "--use-buildtree",
            "--",
            "cat",
            "test",
        ],
    )

    # In this case, we should succeed every time, regardless of what was
    # originally available in the local cache.
    #
    result.assert_success()
    assert "Hi" in result.output


#
# Test behavior of shelling into a buildtree by its artifact name
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_shell_pull_artifact_cached_buildtree(share_with_buildtrees, datafiles, cli):
    project = str(datafiles)
    artifact_name = "test/build-shell-buildtree/4a47c98a10df39e65e99d471f96edc5b58d4ea5b9b1f221d0be832a8124b8099"

    cli.configure({"artifacts": {"servers": [{"url": share_with_buildtrees.repo}]}})

    # Run the shell and request that required artifacts and buildtrees should be pulled
    result = cli.run(
        project=project,
        args=[
            "--pull-buildtrees",
            "shell",
            "--build",
            "--use-buildtree",
            artifact_name,
            "--",
            "cat",
            # We don't preserve the working directory in artifacts, so we will be executing at /
            "/buildstream/test/build-shell/buildtree.bst/test",
        ],
    )

    # In this case, we should succeed every time, regardless of what was
    # originally available in the local cache.
    #
    result.assert_success()
    assert "Hi" in result.output


#
# Test behavior of launching a shell and requesting to use a buildtree.
#
# In this case we download everything we need first, but the buildtree was never cached at build time
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_shell_use_uncached_buildtree(share_without_buildtrees, datafiles, cli):
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"

    cli.configure({"artifacts": {"servers": [{"url": share_without_buildtrees.repo}]}})

    # Pull everything we would need
    maybe_pull_deps(cli, project, element_name, "all", True)

    # Run the shell without asking it to pull any buildtree, just asking to use a buildtree
    result = cli.run(project=project, args=["shell", "--build", element_name, "--use-buildtree", "--", "cat", "test"])

    # Sorry, a buildtree was never cached for this element
    result.assert_main_error(ErrorDomain.APP, "missing-buildtree-artifact-created-without-buildtree")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_shell_script_element(datafiles, cli_integration):
    project = str(datafiles)
    element_name = "build-shell/script.bst"

    result = cli_integration.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
    result.assert_success()

    # Run the shell and use the cached buildtree on this script element
    result = cli_integration.run(
        project=project, args=["shell", "--build", element_name, "--use-buildtree", "--", "cat", "/test"]
    )

    result.assert_success()
    assert "Hi" in result.output


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.parametrize(
    "element_name,expect_success",
    [
        # Build shell into a compose element which succeeded
        ("build-shell/compose-success.bst", True),
        # Build shell into a compose element with failed integration commands
        ("build-shell/compose-fail.bst", False),
    ],
    ids=["integration-success", "integration-fail"],
)
def test_shell_compose_element(datafiles, cli_integration, element_name, expect_success):
    project = str(datafiles)

    # Build the element so it's in the local cache, ensure caching of buildtrees at build time
    result = cli_integration.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
    if expect_success:
        result.assert_success()
    else:
        result.assert_main_error(ErrorDomain.STREAM, None)

    # Ensure that the shell works regardless of success expectations
    #
    result = cli_integration.run(
        project=project, args=["shell", "--build", element_name, "--use-buildtree", "--", "echo", "Hi"]
    )
    result.assert_success()
    assert "Hi" in result.output

    # Check the file created with integration commands
    #
    result = cli_integration.run(
        project=project,
        args=["shell", "--build", element_name, "--use-buildtree", "--", "cat", "/integration-success"],
    )
    if expect_success:
        result.assert_success()
        assert "Hi" in result.output
    else:
        # Here the exit code is determined by `cat`, and will be non-zero.
        #
        # We cannot use result.assert_main_error() because that explicitly expects -1
        assert result.exit_code != 0
