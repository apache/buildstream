import os
import shutil
import pytest
from tests.testutils import cli, create_artifact_share, generate_junction


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
#  * `bst build` pushes all build elements to configured 'push' cache
#  * `bst pull --deps all` downloads everything from cache after local deletion
#
@pytest.mark.datafiles(DATA_DIR)
def test_push_pull_all(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare')) as share:

        # First build the target element and push to the remote.
        cli.configure({
            'artifacts': {'url': share.repo, 'push': True}
        })
        result = cli.run(project=project, args=['build', 'target.bst'])
        result.assert_success()
        assert cli.get_element_state(project, 'target.bst') == 'cached'

        # Assert that everything is now cached in the remote.
        all_elements = ['target.bst', 'import-bin.bst', 'import-dev.bst', 'compose-all.bst']
        for element_name in all_elements:
            assert_shared(cli, share, project, element_name)

        # Now we've pushed, delete the user's local artifact cache
        # directory and try to redownload it from the share
        #
        artifacts = os.path.join(cli.directory, 'artifacts')
        shutil.rmtree(artifacts)

        # Assert that nothing is cached locally anymore
        states = cli.get_element_states(project, all_elements)
        assert not any(states[e] == 'cached' for e in all_elements)

        # Now try bst pull
        result = cli.run(project=project, args=['artifact', 'pull', '--deps', 'all', 'target.bst'])
        result.assert_success()

        # And assert that it's again in the local cache, without having built
        states = cli.get_element_states(project, all_elements)
        assert not any(states[e] != 'cached' for e in all_elements)


# Tests that:
#
#  * `bst push` (default targets) pushes all built elements to configured 'push' cache
#  * `bst pull` (default targets) downloads everything from cache after local deletion
#
@pytest.mark.datafiles(DATA_DIR + '_world')
def test_push_pull_default_targets(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare')) as share:

        # First build the target elements
        cli.configure({
            'artifacts': {'url': share.repo}
        })
        result = cli.run(project=project, args=['build'])
        result.assert_success()
        assert cli.get_element_state(project, 'target.bst') == 'cached'

        # Push all elements
        cli.configure({
            'artifacts': {'url': share.repo, 'push': True}
        })
        result = cli.run(project=project, args=['artifact', 'push'])
        result.assert_success()

        # Assert that everything is now cached in the remote.
        all_elements = ['target.bst', 'import-bin.bst', 'import-dev.bst', 'compose-all.bst']
        for element_name in all_elements:
            assert_shared(cli, share, project, element_name)

        # Now we've pushed, delete the user's local artifact cache
        # directory and try to redownload it from the share
        #
        artifacts = os.path.join(cli.directory, 'artifacts')
        shutil.rmtree(artifacts)

        # Assert that nothing is cached locally anymore
        states = cli.get_element_states(project, all_elements)
        assert not any(states[e] == 'cached' for e in all_elements)

        # Now try bst pull
        result = cli.run(project=project, args=['artifact', 'pull'])
        result.assert_success()

        # And assert that it's again in the local cache, without having built
        states = cli.get_element_states(project, all_elements)
        assert not any(states[e] != 'cached' for e in all_elements)


# Tests that:
#
#  * `bst build` pushes all build elements ONLY to configured 'push' cache
#  * `bst pull` finds artifacts that are available only in the secondary cache
#
@pytest.mark.datafiles(DATA_DIR)
def test_pull_secondary_cache(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare1')) as share1,\
        create_artifact_share(os.path.join(str(tmpdir), 'artifactshare2')) as share2:

        # Build the target and push it to share2 only.
        cli.configure({
            'artifacts': [
                {'url': share1.repo, 'push': False},
                {'url': share2.repo, 'push': True},
            ]
        })
        result = cli.run(project=project, args=['build', 'target.bst'])
        result.assert_success()

        assert_not_shared(cli, share1, project, 'target.bst')
        assert_shared(cli, share2, project, 'target.bst')

        # Delete the user's local artifact cache.
        artifacts = os.path.join(cli.directory, 'artifacts')
        shutil.rmtree(artifacts)

        # Assert that the element is not cached anymore.
        assert cli.get_element_state(project, 'target.bst') != 'cached'

        # Now try bst pull
        result = cli.run(project=project, args=['artifact', 'pull', 'target.bst'])
        result.assert_success()

        # And assert that it's again in the local cache, without having built,
        # i.e. we found it in share2.
        assert cli.get_element_state(project, 'target.bst') == 'cached'


# Tests that:
#
#  * `bst push --remote` pushes to the given remote, not one from the config
#  * `bst pull --remote` pulls from the given remote
#
@pytest.mark.datafiles(DATA_DIR)
def test_push_pull_specific_remote(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    with create_artifact_share(os.path.join(str(tmpdir), 'goodartifactshare')) as good_share,\
        create_artifact_share(os.path.join(str(tmpdir), 'badartifactshare')) as bad_share:

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
            'artifact', 'push', 'target.bst', '--remote', good_share.repo
        ])
        result.assert_success()

        # Assert that all the artifacts are in the share we pushed
        # to, and not the other.
        assert_shared(cli, good_share, project, 'target.bst')
        assert_not_shared(cli, bad_share, project, 'target.bst')

        # Now we've pushed, delete the user's local artifact cache
        # directory and try to redownload it from the good_share.
        #
        artifacts = os.path.join(cli.directory, 'artifacts')
        shutil.rmtree(artifacts)

        result = cli.run(project=project, args=['artifact', 'pull', 'target.bst', '--remote',
                                                good_share.repo])
        result.assert_success()

        # And assert that it's again in the local cache, without having built
        assert cli.get_element_state(project, 'target.bst') == 'cached'


# Tests that:
#
#  * In non-strict mode, dependency changes don't block artifact reuse
#
@pytest.mark.datafiles(DATA_DIR)
def test_push_pull_non_strict(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare')) as share:
        workspace = os.path.join(str(tmpdir), 'workspace')

        # First build the target element and push to the remote.
        cli.configure({
            'artifacts': {'url': share.repo, 'push': True},
            'projects': {
                'test': {'strict': False}
            }
        })
        result = cli.run(project=project, args=['build', 'target.bst'])
        result.assert_success()
        assert cli.get_element_state(project, 'target.bst') == 'cached'

        # Assert that everything is now cached in the remote.
        all_elements = ['target.bst', 'import-bin.bst', 'import-dev.bst', 'compose-all.bst']
        for element_name in all_elements:
            assert_shared(cli, share, project, element_name)

        # Now we've pushed, delete the user's local artifact cache
        # directory and try to redownload it from the share
        #
        artifacts = os.path.join(cli.directory, 'artifacts')
        shutil.rmtree(artifacts)

        # Assert that nothing is cached locally anymore
        for element_name in all_elements:
            assert cli.get_element_state(project, element_name) != 'cached'

        # Add a file to force change in strict cache key of import-bin.bst
        with open(os.path.join(str(project), 'files', 'bin-files', 'usr', 'bin', 'world'), 'w') as f:
            f.write('world')

        # Assert that the workspaced element requires a rebuild
        assert cli.get_element_state(project, 'import-bin.bst') == 'buildable'
        # Assert that the target is still waiting due to --no-strict
        assert cli.get_element_state(project, 'target.bst') == 'waiting'

        # Now try bst pull
        result = cli.run(project=project, args=['artifact', 'pull', '--deps', 'all', 'target.bst'])
        result.assert_success()

        # And assert that the target is again in the local cache, without having built
        assert cli.get_element_state(project, 'target.bst') == 'cached'


# Regression test for https://gitlab.com/BuildStream/buildstream/issues/202
@pytest.mark.datafiles(DATA_DIR)
def test_push_pull_track_non_strict(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare')) as share:

        # First build the target element and push to the remote.
        cli.configure({
            'artifacts': {'url': share.repo, 'push': True},
            'projects': {
                'test': {'strict': False}
            }
        })
        result = cli.run(project=project, args=['build', 'target.bst'])
        result.assert_success()
        assert cli.get_element_state(project, 'target.bst') == 'cached'

        # Assert that everything is now cached in the remote.
        all_elements = {'target.bst', 'import-bin.bst', 'import-dev.bst', 'compose-all.bst'}
        for element_name in all_elements:
            assert_shared(cli, share, project, element_name)

        # Now we've pushed, delete the user's local artifact cache
        # directory and try to redownload it from the share
        #
        artifacts = os.path.join(cli.directory, 'artifacts')
        shutil.rmtree(artifacts)

        # Assert that nothing is cached locally anymore
        for element_name in all_elements:
            assert cli.get_element_state(project, element_name) != 'cached'

        # Now try bst build with tracking and pulling.
        # Tracking will be skipped for target.bst as it doesn't have any sources.
        # With the non-strict build plan target.bst immediately enters the pull queue.
        # However, pulling has to be deferred until the dependencies have been
        # tracked as the strict cache key needs to be calculated before querying
        # the caches.
        result = cli.run(project=project, args=['build', '--track-all', '--all', 'target.bst'])
        result.assert_success()
        assert set(result.get_pulled_elements()) == all_elements


@pytest.mark.datafiles(DATA_DIR)
def test_push_pull_cross_junction(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare')) as share:
        subproject_path = os.path.join(project, 'files', 'sub-project')
        junction_path = os.path.join(project, 'elements', 'junction.bst')

        generate_junction(tmpdir, subproject_path, junction_path, store_ref=True)

        # First build the target element and push to the remote.
        cli.configure({
            'artifacts': {'url': share.repo, 'push': True}
        })
        result = cli.run(project=project, args=['build', 'junction.bst:import-etc.bst'])
        result.assert_success()
        assert cli.get_element_state(project, 'junction.bst:import-etc.bst') == 'cached'

        cache_dir = os.path.join(project, 'cache', 'artifacts')
        shutil.rmtree(cache_dir)

        assert cli.get_element_state(project, 'junction.bst:import-etc.bst') == 'buildable'

        # Now try bst pull
        result = cli.run(project=project, args=['artifact', 'pull', 'junction.bst:import-etc.bst'])
        result.assert_success()

        # And assert that it's again in the local cache, without having built
        assert cli.get_element_state(project, 'junction.bst:import-etc.bst') == 'cached'


@pytest.mark.datafiles(DATA_DIR)
def test_pull_missing_blob(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare')) as share:

        # First build the target element and push to the remote.
        cli.configure({
            'artifacts': {'url': share.repo, 'push': True}
        })
        result = cli.run(project=project, args=['build', 'target.bst'])
        result.assert_success()
        assert cli.get_element_state(project, 'target.bst') == 'cached'

        # Assert that everything is now cached in the remote.
        all_elements = ['target.bst', 'import-bin.bst', 'import-dev.bst', 'compose-all.bst']
        for element_name in all_elements:
            assert_shared(cli, share, project, element_name)

        # Now we've pushed, delete the user's local artifact cache
        # directory and try to redownload it from the share
        #
        artifacts = os.path.join(cli.directory, 'artifacts')
        shutil.rmtree(artifacts)

        # Assert that nothing is cached locally anymore
        for element_name in all_elements:
            assert cli.get_element_state(project, element_name) != 'cached'

        # Now delete blobs in the remote without deleting the artifact ref.
        # This simulates scenarios with concurrent artifact expiry.
        remote_objdir = os.path.join(share.repodir, 'cas', 'objects')
        shutil.rmtree(remote_objdir)

        # Now try bst build
        result = cli.run(project=project, args=['build', 'target.bst'])
        result.assert_success()

        # Assert that no artifacts were pulled
        assert len(result.get_pulled_elements()) == 0


@pytest.mark.datafiles(DATA_DIR)
def test_pull_missing_notifies_user(caplog, cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    caplog.set_level(1)

    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare')) as share:

        cli.configure({
            'artifacts': {'url': share.repo}
        })
        result = cli.run(project=project, args=['build', 'target.bst'])

        result.assert_success()
        assert not result.get_pulled_elements(), \
            "No elements should have been pulled since the cache was empty"

        assert "INFO    Remote ({}) does not have".format(share.repo) in result.stderr
        assert "SKIPPED Pull" in result.stderr


# Tests that:
#
#  * The bst main option --use-remotes limits remote action
#    as expected for pull jobs
#
@pytest.mark.datafiles(DATA_DIR)
def test_useremotes_cli_options(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare1')) as shareuser,\
        create_artifact_share(os.path.join(str(tmpdir), 'artifactshare2')) as shareproject:

        # Add shareproject repo url to project.conf
        with open(os.path.join(project, "project.conf"), "a") as projconf:
            projconf.write("artifacts:\n  url: {}\n  push: True".format(shareproject.repo))

        # First build the target element and push to the remotes.
        # We need the artifact available in the remotes to test against.
        cli.configure({
            'artifacts': {'url': shareuser.repo, 'push': True}
        })
        result = cli.run(project=project, args=['build', 'target.bst'])
        result.assert_success()
        assert cli.get_element_state(project, 'target.bst') == 'cached'

        # Assert that everything is now cached in the remotes.
        all_elements = ['target.bst', 'import-bin.bst', 'compose-all.bst']
        for element_name in all_elements:
            assert_shared(cli, shareuser, project, element_name)
            assert_shared(cli, shareproject, project, element_name)

        # Now we've pushed, delete the user's local artifact cache
        artifacts = os.path.join(cli.directory, 'artifacts')
        shutil.rmtree(artifacts)

        # Assert that nothing is cached locally anymore
        for element_name in all_elements:
            assert cli.get_element_state(project, element_name) != 'cached'

        # Attempt bst build with --use-remotes set as none, this should lead to
        # a complete rebuild without pulling from either artifact remote cache
        result = cli.run(project=project, args=['--use-remotes', 'none', 'build', 'target.bst'])
        result.assert_success()
        for element_name in all_elements:
            assert element_name not in result.get_pulled_elements()

        # Delete local cache again
        artifacts = os.path.join(cli.directory, 'artifacts')
        shutil.rmtree(artifacts)

        # Attempt bst build with --use-remotes set as user, as the shareuser is
        # passed in as user config and not via a project, assert project remote
        # was not attempted by it not being in the output
        result = cli.run(project=project, args=['--use-remotes', 'user', 'build', 'target.bst'])
        result.assert_success()
        for element_name in all_elements:
            assert element_name in result.get_pulled_elements()
        assert shareproject.repo not in result.stderr

        # Delete local cache again
        artifacts = os.path.join(cli.directory, 'artifacts')
        shutil.rmtree(artifacts)

        # Attempt bst build with --use-remotes set as all, this time
        # assert that project remote is attempted and in the output
        result = cli.run(project=project, args=['--use-remotes', 'all', 'build', 'target.bst'])
        result.assert_success()
        for element_name in all_elements:
            assert element_name in result.get_pulled_elements()
        assert shareproject.repo in result.stderr
