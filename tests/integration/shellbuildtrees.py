# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import shutil

import pytest

from buildstream.testing import cli, cli_integration  # pylint: disable=unused-import
from buildstream.exceptions import ErrorDomain
from buildstream.testing._utils.site import HAVE_SANDBOX

from tests.testutils import create_artifact_share


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_buildtree_staged(cli_integration, datafiles):
    # We can only test the non interacitve case
    # The non interactive case defaults to not using buildtrees
    # for `bst shell --build`
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"

    res = cli_integration.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
    res.assert_success()

    res = cli_integration.run(project=project, args=["shell", "--build", element_name, "--", "cat", "test"])
    res.assert_shell_error()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_buildtree_staged_forced_true(cli_integration, datafiles):
    # Test that if we ask for a build tree it is there.
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"

    res = cli_integration.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
    res.assert_success()

    res = cli_integration.run(
        project=project, args=["shell", "--build", "--use-buildtree", "always", element_name, "--", "cat", "test"]
    )
    res.assert_success()
    assert "Hi" in res.output


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_buildtree_staged_warn_empty_cached(cli_integration, tmpdir, datafiles):
    # Test that if we stage a cached and empty buildtree, we warn the user.
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"

    # Switch to a temp artifact cache dir to ensure the artifact is rebuilt,
    # without caching a buildtree which is the default bst behaviour
    cli_integration.configure({"cachedir": str(tmpdir)})

    res = cli_integration.run(project=project, args=["build", element_name])
    res.assert_success()

    res = cli_integration.run(
        project=project, args=["shell", "--build", "--use-buildtree", "always", element_name, "--", "cat", "test"]
    )
    res.assert_main_error(ErrorDomain.APP, None)
    assert "Artifact was created without buildtree, unable to launch shell with it" in res.stderr

    # Now attempt the same with the try option, this should not attempt to find a buildtree
    # and just launch the shell, however the cat should still fail.
    res = cli_integration.run(
        project=project, args=["shell", "--build", "--use-buildtree", "try", element_name, "--", "cat", "test"]
    )
    assert "Artifact created without buildtree, shell will be loaded without it" in res.stderr
    assert "Hi" not in res.output


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_buildtree_staged_if_available(cli_integration, datafiles):
    # Test that a build tree can be correctly detected.
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"

    res = cli_integration.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
    res.assert_success()

    res = cli_integration.run(
        project=project, args=["shell", "--build", "--use-buildtree", "try", element_name, "--", "cat", "test"]
    )
    res.assert_success()
    assert "Hi" in res.output


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_buildtree_staged_forced_false(cli_integration, datafiles):
    # Test that if we ask not to have a build tree it is not there
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"

    res = cli_integration.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
    res.assert_success()

    res = cli_integration.run(
        project=project, args=["shell", "--build", "--use-buildtree", "never", element_name, "--", "cat", "test"]
    )
    res.assert_shell_error()

    assert "Hi" not in res.output


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
        project=project, args=["shell", "--build", element_name, "--use-buildtree", "always", "--", "cat", "test"]
    )
    res.assert_success()
    assert "WARNING: using a buildtree from a failed build" in res.stderr
    assert "Hi" in res.output


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_buildtree_from_failure_option_never(cli_integration, tmpdir, datafiles):

    project = str(datafiles)
    element_name = "build-shell/buildtree-fail.bst"

    # Switch to a temp artifact cache dir to ensure the artifact is rebuilt,
    # without caching a buildtree explicitly
    cli_integration.configure({"cachedir": str(tmpdir)})

    res = cli_integration.run(project=project, args=["--cache-buildtrees", "never", "build", element_name])
    res.assert_main_error(ErrorDomain.STREAM, None)

    res = cli_integration.run(
        project=project, args=["shell", "--build", element_name, "--use-buildtree", "always", "--", "cat", "test"]
    )
    res.assert_main_error(ErrorDomain.APP, None)
    assert "Artifact was created without buildtree, unable to launch shell with it" in res.stderr


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_buildtree_from_failure_option_always(cli_integration, tmpdir, datafiles):

    project = str(datafiles)
    element_name = "build-shell/buildtree-fail.bst"

    # build with  --cache-buildtrees set to 'always', behaviour should match
    # default behaviour (which is always) as the buildtree will explicitly have been
    # cached with content.
    cli_integration.configure({"cachedir": str(tmpdir)})

    res = cli_integration.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
    res.assert_main_error(ErrorDomain.STREAM, None)

    res = cli_integration.run(
        project=project, args=["shell", "--build", element_name, "--use-buildtree", "always", "--", "cat", "test"]
    )
    res.assert_success()
    assert "WARNING: using a buildtree from a failed build" in res.stderr
    assert "Hi" in res.output


# Check that build shells work when pulled from a remote cache
# This is to roughly simulate remote execution
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_buildtree_pulled(cli, tmpdir, datafiles):
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:
        # Build the element to push it to cache
        cli.configure({"artifacts": {"url": share.repo, "push": True}})
        result = cli.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
        result.assert_success()
        assert cli.get_element_state(project, element_name) == "cached"

        # Discard the cache
        shutil.rmtree(str(os.path.join(str(tmpdir), "cache", "cas")))
        shutil.rmtree(str(os.path.join(str(tmpdir), "cache", "artifacts")))
        assert cli.get_element_state(project, element_name) != "cached"

        # Pull from cache, ensuring cli options is set to pull the buildtree
        result = cli.run(
            project=project, args=["--pull-buildtrees", "artifact", "pull", "--deps", "all", element_name]
        )
        result.assert_success()

        # Check it's using the cached build tree
        res = cli.run(
            project=project, args=["shell", "--build", element_name, "--use-buildtree", "always", "--", "cat", "test"]
        )
        res.assert_success()


# This test checks for correct behaviour if a buildtree is not present in the local cache.
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_buildtree_options(cli, tmpdir, datafiles):
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:
        # Build the element to push it to cache
        cli.configure({"artifacts": {"url": share.repo, "push": True}})
        result = cli.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
        result.assert_success()
        assert cli.get_element_state(project, element_name) == "cached"
        assert share.get_artifact(cli.get_artifact_name(project, "test", element_name))

        # Discard the cache
        shutil.rmtree(str(os.path.join(str(tmpdir), "cache", "cas")))
        shutil.rmtree(str(os.path.join(str(tmpdir), "cache", "artifacts")))
        assert cli.get_element_state(project, element_name) != "cached"

        # Pull from cache, but do not include buildtrees.
        result = cli.run(project=project, args=["artifact", "pull", "--deps", "all", element_name])
        result.assert_success()

        # Check it's not using the cached build tree
        res = cli.run(
            project=project, args=["shell", "--build", element_name, "--use-buildtree", "never", "--", "cat", "test"]
        )
        res.assert_shell_error()
        assert "Hi" not in res.output

        # Check it's not using the cached build tree, default is to ask, and fall back to not
        # for non interactive behavior
        res = cli.run(project=project, args=["shell", "--build", element_name, "--", "cat", "test"])
        res.assert_shell_error()
        assert "Hi" not in res.output

        # Check correctly handling the lack of buildtree, with 'try' not attempting to
        # pull the buildtree as the user context is by default set to not pull them
        # and --pull not given
        res = cli.run(
            project=project, args=["shell", "--build", element_name, "--use-buildtree", "try", "--", "cat", "test"]
        )
        assert "Hi" not in res.output
        assert "Attempting to fetch missing artifact buildtrees" not in res.stderr
        assert "WARNING: buildtree is not cached locally, shell will be loaded without it" in res.stderr

        # Check correctly handling the lack of buildtree, with 'try' attempting and succeeding
        # to pull the buildtree as the user context allow the pulling of buildtrees and it is
        # available in the remote and --pull given
        res = cli.run(
            project=project,
            args=[
                "--pull-buildtrees",
                "shell",
                "--build",
                element_name,
                "--pull",
                "--use-buildtree",
                "try",
                "--",
                "cat",
                "test",
            ],
        )
        assert "Attempting to fetch missing artifact buildtree" in res.stderr
        assert "Hi" in res.output
        shutil.rmtree(os.path.join(os.path.join(str(tmpdir), "cache", "cas")))
        shutil.rmtree(os.path.join(os.path.join(str(tmpdir), "cache", "artifacts")))
        assert cli.get_element_state(project, element_name) != "cached"

        # Check it's not loading the shell at all with always set for the buildtree, when the
        # user context does not allow for buildtree pulling and --pull is not given
        result = cli.run(project=project, args=["artifact", "pull", "--deps", "all", element_name])
        result.assert_success()
        res = cli.run(
            project=project, args=["shell", "--build", element_name, "--use-buildtree", "always", "--", "cat", "test"]
        )
        res.assert_main_error(ErrorDomain.APP, None)
        assert (
            "Artifact has a buildtree but it isn't cached. Can be retried with --pull and pull-buildtrees configured"
            in res.stderr
        )
        assert "Hi" not in res.output
        assert "Attempting to fetch missing artifact buildtree" not in res.stderr

        # Check that when user context is set to pull buildtrees and a remote has the buildtree,
        # 'always' will attempt and succeed at pulling the missing buildtree with --pull set.
        res = cli.run(
            project=project,
            args=[
                "--pull-buildtrees",
                "shell",
                "--build",
                element_name,
                "--pull",
                "--use-buildtree",
                "always",
                "--",
                "cat",
                "test",
            ],
        )
        assert "Hi" in res.output
        assert (
            "buildtree is not cached locally but did exist, will attempt to pull from available remotes" in res.stderr
        )
        assert "Attempting to fetch missing artifact buildtree" in res.stderr


# Tests running pull and pull-buildtree options at the same time.
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_pull_buildtree_pulled(cli, tmpdir, datafiles):
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:
        # Build the element to push it to cache
        cli.configure({"artifacts": {"url": share.repo, "push": True}})
        result = cli.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
        result.assert_success()
        assert cli.get_element_state(project, element_name) == "cached"

        # Discard the cache
        shutil.rmtree(str(os.path.join(str(tmpdir), "cache", "cas")))
        shutil.rmtree(str(os.path.join(str(tmpdir), "cache", "artifacts")))
        assert cli.get_element_state(project, element_name) != "cached"

        # Check it's not using the cached build tree, because --pull
        # and pull-buildtrees were not both set
        res = cli.run(
            project=project,
            args=["shell", "--build", element_name, "--pull", "--use-buildtree", "always", "--", "cat", "test",],
        )
        res.assert_main_error(ErrorDomain.APP, None)
        assert "Artifact not cached locally. Can be retried with --pull and pull-buildtrees configured" in res.stderr

        # Check it's using the cached build tree, because --pull
        # and pull-buildtrees were both set
        res = cli.run(
            project=project,
            args=[
                "--pull-buildtrees",
                "shell",
                "--build",
                element_name,
                "--pull",
                "--use-buildtree",
                "always",
                "--",
                "cat",
                "test",
            ],
        )
        result.assert_success()
        assert "Hi" in res.output
