import os
import shutil
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


# Assert that a given artifact is NOT in the share
#
def assert_not_shared(cli, share, project, element_name):
    # NOTE: 'test' here is the name of the project
    # specified in the project.conf we are testing with.
    #
    cache_key = cli.get_element_key(project, element_name)
    if share.has_artifact('test', element_name, cache_key):
        raise AssertionError("Artifact share at {} unexpectedly contains the element {}"
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
def test_push_pull(cli, tmpdir, datafiles, override_urls, project_urls, user_urls):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    share = create_artifact_share(os.path.join(str(tmpdir), 'artifactshare'))

    # First build it without the artifact cache configured
    result = cli.run(project=project, args=['build', 'import-bin.bst'])
    result.assert_success()

    # Assert that we are now cached locally
    assert cli.get_element_state(project, 'import-bin.bst') == 'cached'

    override_urls = [share.repo if url == 'share.repo' else url for url in override_urls]
    project_urls = [share.repo if url == 'share.repo' else url for url in project_urls]
    user_urls = [share.repo if url == 'share.repo' else url for url in user_urls]

    # Configure artifact share
    project_conf_file = str(datafiles.join('project.conf'))
    configure_remote_caches(cli, project_conf_file, override_urls, project_urls, user_urls)
    share.update_summary()

    # Now try bst push. This will push to the highest priority cache.
    result = cli.run(project=project, args=['push', 'import-bin.bst'])
    result.assert_success()
    share.update_summary()

    # And finally assert that the artifact is in the share
    assert_shared(cli, share, project, 'import-bin.bst')

    # Now we've pushed, delete the user's local artifact cache
    # directory and try to redownload it from the share
    #
    artifacts = os.path.join(cli.directory, 'artifacts')
    shutil.rmtree(artifacts)

    # Assert that we are now in a downloadable state, nothing
    # is cached locally anymore
    assert cli.get_element_state(project, 'import-bin.bst') == 'downloadable'

    # Now try bst pull
    result = cli.run(project=project, args=['pull', 'import-bin.bst'])
    result.assert_success()

    # And assert that it's again in the local cache, without having built
    assert cli.get_element_state(project, 'import-bin.bst') == 'cached'


@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_push_pull_all(cli, tmpdir, datafiles):
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

    # Now try bst push
    result = cli.run(project=project, args=['push', '--deps', 'all', 'target.bst'])
    result.assert_success()
    share.update_summary()

    # And finally assert that the artifact is in the share
    all_elements = ['target.bst', 'import-bin.bst', 'import-dev.bst', 'compose-all.bst']
    for element_name in all_elements:
        assert_shared(cli, share, project, element_name)

    # Now we've pushed, delete the user's local artifact cache
    # directory and try to redownload it from the share
    #
    artifacts = os.path.join(cli.directory, 'artifacts')
    shutil.rmtree(artifacts)

    # Assert that we are now in a downloadable state, nothing
    # is cached locally anymore
    for element_name in all_elements:
        assert cli.get_element_state(project, element_name) == 'downloadable'

    # Now try bst pull
    result = cli.run(project=project, args=['pull', '--deps', 'all', 'target.bst'])
    result.assert_success()

    # And assert that it's again in the local cache, without having built
    for element_name in all_elements:
        assert cli.get_element_state(project, element_name) == 'cached'


@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_push_pull_specific_remote(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    good_share = create_artifact_share(os.path.join(str(tmpdir), 'goodartifactshare'))
    bad_share = create_artifact_share(os.path.join(str(tmpdir), 'badartifactshare'))

    # First build it without the artifact cache configured
    result = cli.run(project=project, args=['build', 'target.bst'])
    assert result.exit_code == 0

    # Assert that we are now cached locally
    state = cli.get_element_state(project, 'target.bst')
    assert state == 'cached'

    # Configure only the artifact share that we want to avoid.
    project_conf_file = str(datafiles.join('project.conf'))
    configure_remote_caches(cli, project_conf_file, [bad_share.repo], [bad_share.repo], [bad_share.repo])

    # Now try bst push
    result = cli.run(project=project, args=[
        'push', 'target.bst', '--remote', good_share.repo
    ])
    assert result.exit_code == 0
    good_share.update_summary()
    bad_share.update_summary()

    # Assert that all the artifacts are in the share we pushed
    # to, and not the other.
    assert_shared(cli, good_share, project, 'target.bst')
    assert_not_shared(cli, bad_share, project, 'target.bst')

    # Now we've pushed, delete the user's local artifact cache
    # directory and try to redownload it from the share
    #
    artifacts = os.path.join(cli.directory, 'artifacts')
    shutil.rmtree(artifacts)

    result = cli.run(project=project, args=['pull', 'target.bst', '--remote',
                                            good_share.repo])
    assert result.exit_code == 0

    # And assert that it's again in the local cache, without having built
    assert cli.get_element_state(project, 'target.bst') == 'cached'


@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_pull_secondary_cache(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    share1 = create_artifact_share(os.path.join(str(tmpdir), 'artifactshare1'))
    share2 = create_artifact_share(os.path.join(str(tmpdir), 'artifactshare2'))

    # First build it without the artifact cache configured
    result = cli.run(project=project, args=['build', 'target.bst'])
    assert result.exit_code == 0

    # Assert that we are now cached locally
    state = cli.get_element_state(project, 'target.bst')
    assert state == 'cached'

    # bst push to secondary remote
    result = cli.run(project=project, args=[
        'push', 'target.bst', '--remote', share2.repo
    ])
    assert result.exit_code == 0
    share2.update_summary()

    # Now we've pushed, delete the user's local artifact cache
    artifacts = os.path.join(cli.directory, 'artifacts')
    shutil.rmtree(artifacts)

    # Configure artifact shares
    project_conf_file = str(datafiles.join('project.conf'))
    configure_remote_caches(cli, project_conf_file, [], [share1.repo, share2.repo], [])

    # And assert that it's found in share2
    assert cli.get_element_state(project, 'target.bst') == 'downloadable'
