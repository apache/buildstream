import os
import shutil
import pytest
from tests.testutils import cli, create_artifact_share
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
@pytest.mark.datafiles(DATA_DIR)
def test_push_pull_all(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    share = create_artifact_share(os.path.join(str(tmpdir), 'artifactshare'))

    # First build the target element and push to the remote.
    cli.configure({
        'artifacts': {'url': share.repo, 'push': True}
    })
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    assert cli.get_element_state(project, 'target.bst') == 'cached'

    # Assert that everything is now cached in the remote.
    share.update_summary()
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
def test_pull_secondary_cache(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    share1 = create_artifact_share(os.path.join(str(tmpdir), 'artifactshare1'))
    share2 = create_artifact_share(os.path.join(str(tmpdir), 'artifactshare2'))

    # Build the target and push it to share2 only.
    cli.configure({
        'artifacts': [
            {'url': share1.repo, 'push': False},
            {'url': share2.repo, 'push': True},
        ]
    })
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    share1.update_summary()
    share2.update_summary()

    assert_not_shared(cli, share1, project, 'target.bst')
    assert_shared(cli, share2, project, 'target.bst')

    # Delete the user's local artifact cache.
    artifacts = os.path.join(cli.directory, 'artifacts')
    shutil.rmtree(artifacts)

    # Assert that the element is 'downloadable', i.e. we found it in share2.
    assert cli.get_element_state(project, 'target.bst') == 'downloadable'


@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_push_pull_specific_remote(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    good_share = create_artifact_share(os.path.join(str(tmpdir), 'goodartifactshare'))
    bad_share = create_artifact_share(os.path.join(str(tmpdir), 'badartifactshare'))

    # Build the target so we have it cached locally only.
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    state = cli.get_element_state(project, 'target.bst')
    assert state == 'cached'

    # Configure the default push location to be bad_share; we will assert that
    # nothing actually gets pushed there.
    cli.configure({
        'artifacts': {'url': bad_share.repo, 'push': True},
    })

    # Now try `bst push` to the good_share.
    result = cli.run(project=project, args=[
        'push', 'target.bst', '--remote', good_share.repo
    ])
    result.assert_success()

    good_share.update_summary()
    bad_share.update_summary()

    # Assert that all the artifacts are in the share we pushed
    # to, and not the other.
    assert_shared(cli, good_share, project, 'target.bst')
    assert_not_shared(cli, bad_share, project, 'target.bst')

    # Now we've pushed, delete the user's local artifact cache
    # directory and try to redownload it from the good_share.
    #
    artifacts = os.path.join(cli.directory, 'artifacts')
    shutil.rmtree(artifacts)

    result = cli.run(project=project, args=['pull', 'target.bst', '--remote',
                                            good_share.repo])
    result.assert_success()

    # And assert that it's again in the local cache, without having built
    assert cli.get_element_state(project, 'target.bst') == 'cached'
