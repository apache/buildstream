import os
import pytest
import shutil

from tests.testutils import cli, cli_integration, create_artifact_share
from tests.testutils.site import HAVE_BWRAP, IS_LINUX
from buildstream._exceptions import ErrorDomain


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
def test_buildtree_staged(cli_integration, tmpdir, datafiles):
    # We can only test the non interacitve case
    # The non interactive case defaults to not using buildtrees
    # for `bst shell --build`
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_name = 'build-shell/buildtree.bst'

    res = cli_integration.run(project=project, args=['build', element_name])
    res.assert_success()

    res = cli_integration.run(project=project, args=[
        'shell', '--build', element_name, '--', 'cat', 'test'
    ])
    res.assert_shell_error()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
def test_buildtree_staged_forced_true(cli_integration, tmpdir, datafiles):
    # Test that if we ask for a build tree it is there.
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_name = 'build-shell/buildtree.bst'

    res = cli_integration.run(project=project, args=['build', element_name])
    res.assert_success()

    res = cli_integration.run(project=project, args=[
        'shell', '--build', '--use-buildtree', 'always', element_name, '--', 'cat', 'test'
    ])
    res.assert_success()
    assert 'Hi' in res.output


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
def test_buildtree_staged_if_available(cli_integration, tmpdir, datafiles):
    # Test that a build tree can be correctly detected.
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_name = 'build-shell/buildtree.bst'

    res = cli_integration.run(project=project, args=['build', element_name])
    res.assert_success()

    res = cli_integration.run(project=project, args=[
        'shell', '--build', '--use-buildtree', 'try', element_name, '--', 'cat', 'test'
    ])
    res.assert_success()
    assert 'Hi' in res.output


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
def test_buildtree_staged_forced_false(cli_integration, tmpdir, datafiles):
    # Test that if we ask not to have a build tree it is not there
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_name = 'build-shell/buildtree.bst'

    res = cli_integration.run(project=project, args=['build', element_name])
    res.assert_success()

    res = cli_integration.run(project=project, args=[
        'shell', '--build', '--use-buildtree', 'never', element_name, '--', 'cat', 'test'
    ])
    res.assert_shell_error()

    assert 'Hi' not in res.output


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
def test_buildtree_from_failure(cli_integration, tmpdir, datafiles):
    # Test that we can use a build tree after a failure
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_name = 'build-shell/buildtree-fail.bst'

    res = cli_integration.run(project=project, args=['build', element_name])
    res.assert_main_error(ErrorDomain.STREAM, None)

    # Assert that file has expected contents
    res = cli_integration.run(project=project, args=[
        'shell', '--build', element_name, '--use-buildtree', 'always', '--', 'cat', 'test'
    ])
    res.assert_success()
    assert "Warning: using a buildtree from a failed build" in res.output
    assert 'Hi' in res.output


# Check that build shells work when pulled from a remote cache
# This is to roughly simulate remote execution
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
def test_buildtree_pulled(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_name = 'build-shell/buildtree.bst'

    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare')) as share:
        # Build the element to push it to cache
        cli.configure({
            'artifacts': {'url': share.repo, 'push': True}
        })
        result = cli.run(project=project, args=['build', element_name])
        result.assert_success()
        assert cli.get_element_state(project, element_name) == 'cached'

        # Discard the cache
        cli.configure({
            'artifacts': {'url': share.repo, 'push': True},
            'artifactdir': os.path.join(cli.directory, 'artifacts2')
        })
        assert cli.get_element_state(project, element_name) != 'cached'

        # Pull from cache, ensuring cli options is set to pull the buildtree
        result = cli.run(project=project, args=['--pull-buildtrees', 'pull', '--deps', 'all', element_name])
        result.assert_success()

        # Check it's using the cached build tree
        res = cli.run(project=project, args=[
            'shell', '--build', element_name, '--use-buildtree', 'always', '--', 'cat', 'test'
        ])
        res.assert_success()


# This test checks for correct behaviour if a buildtree is not present.
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
def test_buildtree_options(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_name = 'build-shell/buildtree.bst'

    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare')) as share:
        # Build the element to push it to cache
        cli.configure({
            'artifacts': {'url': share.repo, 'push': True}
        })
        result = cli.run(project=project, args=['build', element_name])
        result.assert_success()
        assert cli.get_element_state(project, element_name) == 'cached'

        # Discard the cache
        cli.configure({
            'artifacts': {'url': share.repo, 'push': True},
            'artifactdir': os.path.join(cli.directory, 'artifacts2')
        })
        assert cli.get_element_state(project, element_name) != 'cached'

        # Pull from cache, but do not include buildtrees.
        result = cli.run(project=project, args=['pull', '--deps', 'all', element_name])
        result.assert_success()

        # The above is the simplest way I know to create a local cache without any buildtrees.

        # Check it's not using the cached build tree
        res = cli.run(project=project, args=[
            'shell', '--build', element_name, '--use-buildtree', 'never', '--', 'cat', 'test'
        ])
        res.assert_shell_error()
        assert 'Hi' not in res.output

        # Check it's not correctly handling the lack of buildtree
        res = cli.run(project=project, args=[
            'shell', '--build', element_name, '--use-buildtree', 'try', '--', 'cat', 'test'
        ])
        res.assert_shell_error()
        assert 'Hi' not in res.output

        # Check it's not using the cached build tree, default is to ask, and fall back to not
        # for non interactive behavior
        res = cli.run(project=project, args=[
            'shell', '--build', element_name, '--', 'cat', 'test'
        ])
        res.assert_shell_error()
        assert 'Hi' not in res.output

        # Check it's using the cached build tree
        res = cli.run(project=project, args=[
            'shell', '--build', element_name, '--use-buildtree', 'always', '--', 'cat', 'test'
        ])
        res.assert_main_error(ErrorDomain.PROG_NOT_FOUND, None)
        assert 'Hi' not in res.output
