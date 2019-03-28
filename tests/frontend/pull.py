# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import shutil
import stat
import pytest
from buildstream import utils
from buildstream.testing import cli  # pylint: disable=unused-import
from tests.testutils import create_artifact_share, generate_junction


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
    if not share.has_artifact(cli.get_artifact_name(project, 'test', element_name)):
        raise AssertionError("Artifact share at {} does not contain the expected element {}"
                             .format(share.repo, element_name))


# Assert that a given artifact is NOT in the share
#
def assert_not_shared(cli, share, project, element_name):
    # NOTE: 'test' here is the name of the project
    # specified in the project.conf we are testing with.
    #
    if share.has_artifact(cli.get_artifact_name(project, 'test', element_name)):
        raise AssertionError("Artifact share at {} unexpectedly contains the element {}"
                             .format(share.repo, element_name))


# Tests that:
#
#  * `bst build` pushes all build elements to configured 'push' cache
#  * `bst artifact pull --deps all` downloads everything from cache after local deletion
#
@pytest.mark.datafiles(DATA_DIR)
def test_push_pull_all(cli, tmpdir, datafiles):
    project = str(datafiles)

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
        casdir = os.path.join(cli.directory, 'cas')
        shutil.rmtree(casdir)
        artifactdir = os.path.join(cli.directory, 'artifacts')
        shutil.rmtree(artifactdir)

        # Assert that nothing is cached locally anymore
        states = cli.get_element_states(project, all_elements)
        assert not any(states[e] == 'cached' for e in all_elements)

        # Now try bst artifact pull
        result = cli.run(project=project, args=['artifact', 'pull', '--deps', 'all', 'target.bst'])
        result.assert_success()

        # And assert that it's again in the local cache, without having built
        states = cli.get_element_states(project, all_elements)
        assert not any(states[e] != 'cached' for e in all_elements)


# Tests that:
#
#  * `bst artifact push` (default targets) pushes all built elements to configured 'push' cache
#  * `bst artifact pull` (default targets) downloads everything from cache after local deletion
#
@pytest.mark.datafiles(DATA_DIR + '_world')
def test_push_pull_default_targets(cli, tmpdir, datafiles):
    project = str(datafiles)

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
        casdir = os.path.join(cli.directory, 'cas')
        shutil.rmtree(casdir)
        artifactdir = os.path.join(cli.directory, 'artifacts')
        shutil.rmtree(artifactdir)

        # Assert that nothing is cached locally anymore
        states = cli.get_element_states(project, all_elements)
        assert not any(states[e] == 'cached' for e in all_elements)

        # Now try bst artifact pull
        result = cli.run(project=project, args=['artifact', 'pull'])
        result.assert_success()

        # And assert that it's again in the local cache, without having built
        states = cli.get_element_states(project, all_elements)
        assert not any(states[e] != 'cached' for e in all_elements)


# Tests that:
#
#  * `bst build` pushes all build elements ONLY to configured 'push' cache
#  * `bst artifact pull` finds artifacts that are available only in the secondary cache
#
@pytest.mark.datafiles(DATA_DIR)
def test_pull_secondary_cache(cli, tmpdir, datafiles):
    project = str(datafiles)

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
        casdir = os.path.join(cli.directory, 'cas')
        shutil.rmtree(casdir)
        artifactdir = os.path.join(cli.directory, 'artifacts')
        shutil.rmtree(artifactdir)

        # Assert that the element is not cached anymore.
        assert cli.get_element_state(project, 'target.bst') != 'cached'

        # Now try bst artifact pull
        result = cli.run(project=project, args=['artifact', 'pull', 'target.bst'])
        result.assert_success()

        # And assert that it's again in the local cache, without having built,
        # i.e. we found it in share2.
        assert cli.get_element_state(project, 'target.bst') == 'cached'


# Tests that:
#
#  * `bst artifact push --remote` pushes to the given remote, not one from the config
#  * `bst artifact pull --remote` pulls from the given remote
#
@pytest.mark.datafiles(DATA_DIR)
def test_push_pull_specific_remote(cli, tmpdir, datafiles):
    project = str(datafiles)

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

        # Now try `bst artifact push` to the good_share.
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
        casdir = os.path.join(cli.directory, 'cas')
        shutil.rmtree(casdir)
        artifactdir = os.path.join(cli.directory, 'artifacts')
        shutil.rmtree(artifactdir)

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
    project = str(datafiles)

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

        # Assert that everything is now cached in the reote.
        all_elements = ['target.bst', 'import-bin.bst', 'import-dev.bst', 'compose-all.bst']
        for element_name in all_elements:
            assert_shared(cli, share, project, element_name)

        # Now we've pushed, delete the user's local artifact cache
        # directory and try to redownload it from the share
        #
        casdir = os.path.join(cli.directory, 'cas')
        shutil.rmtree(casdir)
        artifactdir = os.path.join(cli.directory, 'artifacts')
        shutil.rmtree(artifactdir)

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

        # Now try bst artifact pull
        result = cli.run(project=project, args=['artifact', 'pull', '--deps', 'all', 'target.bst'])
        result.assert_success()

        # And assert that the target is again in the local cache, without having built
        assert cli.get_element_state(project, 'target.bst') == 'cached'


# Regression test for https://gitlab.com/BuildStream/buildstream/issues/202
@pytest.mark.datafiles(DATA_DIR)
def test_push_pull_track_non_strict(cli, tmpdir, datafiles):
    project = str(datafiles)

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
        casdir = os.path.join(cli.directory, 'cas')
        shutil.rmtree(casdir)
        artifactdir = os.path.join(cli.directory, 'artifacts')
        shutil.rmtree(artifactdir)

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
    project = str(datafiles)

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

        cache_dir = os.path.join(project, 'cache', 'cas')
        shutil.rmtree(cache_dir)
        artifact_dir = os.path.join(project, 'cache', 'artifacts')
        shutil.rmtree(artifact_dir)

        assert cli.get_element_state(project, 'junction.bst:import-etc.bst') == 'buildable'

        # Now try bst artifact pull
        result = cli.run(project=project, args=['artifact', 'pull', 'junction.bst:import-etc.bst'])
        result.assert_success()

        # And assert that it's again in the local cache, without having built
        assert cli.get_element_state(project, 'junction.bst:import-etc.bst') == 'cached'


@pytest.mark.datafiles(DATA_DIR)
def test_pull_missing_blob(cli, tmpdir, datafiles):
    project = str(datafiles)

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
        casdir = os.path.join(cli.directory, 'cas')
        shutil.rmtree(casdir)
        artifactdir = os.path.join(cli.directory, 'artifacts')
        shutil.rmtree(artifactdir)

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
        assert not result.get_pulled_elements()


@pytest.mark.datafiles(DATA_DIR)
def test_pull_missing_local_blob(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare')) as share:

        # First build the import-bin element and push to the remote.
        cli.configure({
            'artifacts': {'url': share.repo, 'push': True}
        })
        result = cli.run(project=project, args=['build', 'import-bin.bst'])
        result.assert_success()
        assert cli.get_element_state(project, 'import-bin.bst') == 'cached'

        # Delete a file blob from the local cache.
        # This is a placeholder to test partial CAS handling until we support
        # partial artifact pulling (or blob-based CAS expiry).
        #
        digest = utils.sha256sum(os.path.join(project, 'files', 'bin-files', 'usr', 'bin', 'hello'))
        objpath = os.path.join(cli.directory, 'cas', 'objects', digest[:2], digest[2:])
        os.unlink(objpath)

        # Now try bst build
        result = cli.run(project=project, args=['build', 'target.bst'])
        result.assert_success()

        # Assert that the import-bin artifact was pulled (completing the partial artifact)
        assert result.get_pulled_elements() == ['import-bin.bst']


@pytest.mark.datafiles(DATA_DIR)
def test_pull_missing_notifies_user(caplog, cli, tmpdir, datafiles):
    project = str(datafiles)
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


@pytest.mark.datafiles(DATA_DIR)
def test_build_remote_option(caplog, cli, tmpdir, datafiles):
    project = str(datafiles)
    caplog.set_level(1)

    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare1')) as shareuser,\
        create_artifact_share(os.path.join(str(tmpdir), 'artifactshare2')) as shareproject,\
        create_artifact_share(os.path.join(str(tmpdir), 'artifactshare3')) as sharecli:

        # Add shareproject repo url to project.conf
        with open(os.path.join(project, "project.conf"), "a") as projconf:
            projconf.write("artifacts:\n  url: {}\n  push: True".format(shareproject.repo))

        # Configure shareuser remote in user conf
        cli.configure({
            'artifacts': {'url': shareuser.repo, 'push': True}
        })

        # Push the artifacts to the shareuser and shareproject remotes.
        # Assert that shareuser and shareproject have the artfifacts cached,
        # but sharecli doesn't, then delete locally cached elements
        result = cli.run(project=project, args=['build', 'target.bst'])
        result.assert_success()
        all_elements = ['target.bst', 'import-bin.bst', 'compose-all.bst']
        for element_name in all_elements:
            assert element_name in result.get_pushed_elements()
            assert_not_shared(cli, sharecli, project, element_name)
            assert_shared(cli, shareuser, project, element_name)
            assert_shared(cli, shareproject, project, element_name)
            cli.remove_artifact_from_cache(project, element_name)

        # Now check that a build with cli set as sharecli results in nothing being pulled,
        # as it doesn't have them cached and shareuser/shareproject should be ignored. This
        # will however result in the artifacts being built and pushed to it
        result = cli.run(project=project, args=['build', '--remote', sharecli.repo, 'target.bst'])
        result.assert_success()
        for element_name in all_elements:
            assert element_name not in result.get_pulled_elements()
            assert_shared(cli, sharecli, project, element_name)
            cli.remove_artifact_from_cache(project, element_name)

        # Now check that a clean build with cli set as sharecli should result in artifacts only
        # being pulled from it, as that was provided via the cli and is populated
        result = cli.run(project=project, args=['build', '--remote', sharecli.repo, 'target.bst'])
        result.assert_success()
        for element_name in all_elements:
            assert cli.get_element_state(project, element_name) == 'cached'
            assert element_name in result.get_pulled_elements()
        assert shareproject.repo not in result.stderr
        assert shareuser.repo not in result.stderr
        assert sharecli.repo in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_pull_access_rights(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkout = os.path.join(str(tmpdir), 'checkout')

    # Work-around datafiles not preserving mode
    os.chmod(os.path.join(project, 'files/bin-files/usr/bin/hello'), 0o0755)

    # We need a big file that does not go into a batch to test a different
    # code path
    os.makedirs(os.path.join(project, 'files/dev-files/usr/share'), exist_ok=True)
    with open(os.path.join(project, 'files/dev-files/usr/share/big-file'), 'w') as f:
        buf = ' ' * 4096
        for _ in range(1024):
            f.write(buf)

    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare')) as share:

        cli.configure({
            'artifacts': {'url': share.repo, 'push': True}
        })
        result = cli.run(project=project, args=['build', 'compose-all.bst'])
        result.assert_success()

        result = cli.run(project=project,
                         args=['artifact', 'checkout',
                               '--hardlinks', '--no-integrate',
                               'compose-all.bst',
                               '--directory', checkout])
        result.assert_success()

        st = os.lstat(os.path.join(checkout, 'usr/include/pony.h'))
        assert stat.S_ISREG(st.st_mode)
        assert stat.S_IMODE(st.st_mode) == 0o0644

        st = os.lstat(os.path.join(checkout, 'usr/bin/hello'))
        assert stat.S_ISREG(st.st_mode)
        assert stat.S_IMODE(st.st_mode) == 0o0755

        st = os.lstat(os.path.join(checkout, 'usr/share/big-file'))
        assert stat.S_ISREG(st.st_mode)
        assert stat.S_IMODE(st.st_mode) == 0o0644

        shutil.rmtree(checkout)

        casdir = os.path.join(cli.directory, 'cas')
        shutil.rmtree(casdir)

        result = cli.run(project=project, args=['artifact', 'pull', 'compose-all.bst'])
        result.assert_success()

        result = cli.run(project=project,
                         args=['artifact', 'checkout',
                               '--hardlinks', '--no-integrate',
                               'compose-all.bst',
                               '--directory', checkout])
        result.assert_success()

        st = os.lstat(os.path.join(checkout, 'usr/include/pony.h'))
        assert stat.S_ISREG(st.st_mode)
        assert stat.S_IMODE(st.st_mode) == 0o0644

        st = os.lstat(os.path.join(checkout, 'usr/bin/hello'))
        assert stat.S_ISREG(st.st_mode)
        assert stat.S_IMODE(st.st_mode) == 0o0755

        st = os.lstat(os.path.join(checkout, 'usr/share/big-file'))
        assert stat.S_ISREG(st.st_mode)
        assert stat.S_IMODE(st.st_mode) == 0o0644
