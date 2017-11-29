import os
import pytest
from tests.testutils import cli, create_artifact_share
from tests.testutils.site import IS_LINUX

from buildstream import _yaml

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
    'override_url, project_url, user_url',
    [
        pytest.param('', '', 'share.repo', id='user-config'),
        pytest.param('', 'share.repo', '/tmp/share/user', id='project-config'),
        pytest.param('share.repo', '/tmp/share/project', '/tmp/share/user', id='project-override-in-user-config'),
    ])
@pytest.mark.datafiles(DATA_DIR)
def test_push(cli, tmpdir, datafiles, override_url, user_url, project_url):
    project = str(datafiles)
    share = create_artifact_share(os.path.join(str(tmpdir), 'artifactshare'))

    # First build it without the artifact cache configured
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    # Assert that we are now cached locally
    assert cli.get_element_state(project, 'target.bst') == 'cached'

    override_url = share.repo if override_url == 'share.repo' else override_url
    project_url = share.repo if project_url == 'share.repo' else project_url
    user_url = share.repo if user_url == 'share.repo' else user_url

    # Configure artifact share
    cli.configure({
        'artifacts': {
            'url': user_url,
        },
        'projects': {
            'test': {
                'artifacts': {
                    'url': override_url,
                }
            }
        }
    })

    if project_url:
        project_conf_file = str(datafiles.join('project.conf'))
        project_config = _yaml.load(project_conf_file)
        project_config.update({
            'artifacts': {
                'url': project_url,
            }
        })
        _yaml.dump(_yaml.node_sanitize(project_config), filename=project_conf_file)

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
