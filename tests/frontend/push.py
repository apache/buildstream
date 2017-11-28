import os
import pytest
from tests.testutils import cli, create_artifact_share, configure_remote_caches
from tests.testutils.site import IS_LINUX

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


# Assert that a given artifact is in the share
#
def assert_shared(cli, share, project, element_name):
    # NOTE: 'test' here is the name of the project
    # specified in the project.conf we are testing with.
    #
    cache_key = cli.get_element_key(project, element_name)
    if not share.has_artifact('test', element_name, cache_key):
        raise AssertionError("Artifact share at {} does not contain the expected element {}"
                             .format(share.repo, element_name))


@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.parametrize(
    'override_urls, project_urls, user_urls',
    [
        # The leftmost cache is the highest priority one.
        pytest.param([], [], ['share.repo', '/tmp/do-not-use/user'], id='user-config'),
        pytest.param([], ['share.repo', '/tmp/do-not-use/project'], ['/tmp/do-not-use/user'], id='project-config'),
        pytest.param(['share.repo'], ['/tmp/do-not-use/project'], ['/tmp/do-not-use/user'],
                     id='project-override-in-user-config'),
    ])
@pytest.mark.datafiles(DATA_DIR)
def test_push(cli, tmpdir, datafiles, user_urls, project_urls, override_urls):
    project = str(datafiles)
    share = create_artifact_share(os.path.join(str(tmpdir), 'artifactshare'))

    # First build it without the artifact cache configured
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    # Assert that we are now cached locally
    assert cli.get_element_state(project, 'target.bst') == 'cached'

    override_urls = [share.repo if url == 'share.repo' else url for url in override_urls]
    project_urls = [share.repo if url == 'share.repo' else url for url in project_urls]
    user_urls = [share.repo if url == 'share.repo' else url for url in user_urls]

    # Configure artifact share
    project_conf_file = str(datafiles.join('project.conf'))
    configure_remote_caches(cli, project_conf_file, override_urls, project_urls, user_urls)

    # Now try bst push
    result = cli.run(project=project, args=['push', 'target.bst'])
    result.assert_success()

    # And finally assert that the artifact is in the share
    assert_shared(cli, share, project, 'target.bst')


@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_push_all(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    share = create_artifact_share(os.path.join(str(tmpdir), 'artifactshare'))

    # First build it without the artifact cache configured
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    # Assert that we are now cached locally
    assert cli.get_element_state(project, 'target.bst') == 'cached'

    # Configure artifact share
    cli.configure({
        #
        # FIXME: This test hangs "sometimes" if we allow
        #        concurrent push.
        #
        #        It's not too bad to ignore since we're
        #        using the local artifact cache functionality
        #        only, but it should probably be fixed.
        #
        'scheduler': {
            'pushers': 1
        },
        'artifacts': {
            'url': share.repo,
        }
    })

    # Now try bst push all the deps
    result = cli.run(project=project, args=[
        'push', 'target.bst',
        '--deps', 'all'
    ])
    result.assert_success()

    # And finally assert that all the artifacts are in the share
    assert_shared(cli, share, project, 'target.bst')
    assert_shared(cli, share, project, 'import-bin.bst')
    assert_shared(cli, share, project, 'import-dev.bst')
    assert_shared(cli, share, project, 'compose-all.bst')
