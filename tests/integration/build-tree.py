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
    # i.e. tests that cached build trees are staged by `bst shell --build`
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_name = 'build-shell/buildtree.bst'

    res = cli_integration.run(project=project, args=['build', element_name])
    res.assert_success()

    res = cli_integration.run(project=project, args=[
        'shell', '--build', element_name, '--', 'grep', '-q', 'Hi', 'test'
    ])
    res.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
def test_buildtree_from_failure(cli_integration, tmpdir, datafiles):
    # i.e. test that on a build failure, we can still shell into it
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_name = 'build-shell/buildtree-fail.bst'

    res = cli_integration.run(project=project, args=['build', element_name])
    res.assert_main_error(ErrorDomain.STREAM, None)

    # Assert that file has expected contents
    res = cli_integration.run(project=project, args=[
        'shell', '--build', element_name, '--', 'cat', 'test'
    ])
    res.assert_success()
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
            'shell', '--build', element_name, '--', 'grep', '-q', 'Hi', 'test'
        ])
        res.assert_success()
