import os
import shutil
import pytest
from buildstream._exceptions import ErrorDomain
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


# Tests that:
#
#  * `bst push` fails if there are no remotes configured for pushing
#  * `bst push` successfully pushes to any remote that is configured for pushing
#
@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_push(cli, tmpdir, datafiles):
    project = str(datafiles)

    # First build the project without the artifact cache configured
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    # Assert that we are now cached locally
    assert cli.get_element_state(project, 'target.bst') == 'cached'

    # Set up two artifact shares.
    share1 = create_artifact_share(os.path.join(str(tmpdir), 'artifactshare1'))
    share2 = create_artifact_share(os.path.join(str(tmpdir), 'artifactshare2'))

    # Try pushing with no remotes configured. This should fail.
    result = cli.run(project=project, args=['push', 'target.bst'])
    result.assert_main_error(ErrorDomain.STREAM, None)

    # Configure bst to pull but not push from a cache and run `bst push`.
    # This should also fail.
    cli.configure({
        'artifacts': {'url': share1.repo, 'push': False},
    })
    result = cli.run(project=project, args=['push', 'target.bst'])
    result.assert_main_error(ErrorDomain.STREAM, None)

    # Configure bst to push to one of the caches and run `bst push`. This works.
    cli.configure({
        'artifacts': [
            {'url': share1.repo, 'push': False},
            {'url': share2.repo, 'push': True},
        ]
    })
    result = cli.run(project=project, args=['push', 'target.bst'])

    assert_not_shared(cli, share1, project, 'target.bst')
    assert_shared(cli, share2, project, 'target.bst')

    # Now try pushing to both (making sure to empty the cache we just pushed
    # to).
    shutil.rmtree(share2.directory)
    share2 = create_artifact_share(os.path.join(str(tmpdir), 'artifactshare2'))
    cli.configure({
        'artifacts': [
            {'url': share1.repo, 'push': True},
            {'url': share2.repo, 'push': True},
        ]
    })
    result = cli.run(project=project, args=['push', 'target.bst'])

    assert_shared(cli, share1, project, 'target.bst')
    assert_shared(cli, share2, project, 'target.bst')


# Tests that `bst push --deps all` pushes all dependencies of the given element.
#
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
            'push': True,
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


# Tests that `bst build` won't push artifacts to the cache it just pulled from.
#
# Regression test for https://gitlab.com/BuildStream/buildstream/issues/233.
@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_push_after_pull(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # Set up two artifact shares.
    share1 = create_artifact_share(os.path.join(str(tmpdir), 'artifactshare1'))
    share2 = create_artifact_share(os.path.join(str(tmpdir), 'artifactshare2'))

    # Set the scene: share1 has the artifact, share2 does not.
    #
    cli.configure({
        'artifacts': {'url': share1.repo, 'push': True},
    })

    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    cli.remove_artifact_from_cache(project, 'target.bst')

    assert_shared(cli, share1, project, 'target.bst')
    assert_not_shared(cli, share2, project, 'target.bst')
    assert cli.get_element_state(project, 'target.bst') != 'cached'

    # Now run the build again. Correct `bst build` behaviour is to download the
    # artifact from share1 but not push it back again.
    #
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    assert result.get_pulled_elements() == ['target.bst']
    assert result.get_pushed_elements() == []

    # Delete the artifact locally again.
    cli.remove_artifact_from_cache(project, 'target.bst')

    # Now we add share2 into the mix as a second push remote. This time,
    # `bst build` should push to share2 after pulling from share1.
    cli.configure({
        'artifacts': [
            {'url': share1.repo, 'push': True},
            {'url': share2.repo, 'push': True},
        ]
    })
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    assert result.get_pulled_elements() == ['target.bst']
    assert result.get_pushed_elements() == ['target.bst']
