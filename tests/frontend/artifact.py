#
#  Copyright (C) 2018 Codethink Limited
#  Copyright (C) 2018 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors: Richard Maw <richard.maw@codethink.co.uk>
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.element import _get_normal_name
from buildstream._exceptions import ErrorDomain
from buildstream.testing import cli  # pylint: disable=unused-import
from tests.testutils import create_artifact_share


# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


@pytest.mark.datafiles(DATA_DIR)
def test_artifact_log(cli, datafiles):
    project = str(datafiles)

    # Get the cache key of our test element
    result = cli.run(project=project, silent=True, args=[
        '--no-colors',
        'show', '--deps', 'none', '--format', '%{full-key}',
        'target.bst'
    ])
    key = result.output.strip()

    # Ensure we have an artifact to read
    result = cli.run(project=project, args=['build', 'target.bst'])
    assert result.exit_code == 0

    # Read the log via the element name
    result = cli.run(project=project, args=['artifact', 'log', 'target.bst'])
    assert result.exit_code == 0
    log = result.output

    # Assert that there actually was a log file
    assert log != ''

    # Read the log via the key
    result = cli.run(project=project, args=['artifact', 'log', 'test/target/' + key])
    assert result.exit_code == 0
    assert log == result.output

    # Read the log via glob
    result = cli.run(project=project, args=['artifact', 'log', 'test/target/*'])
    assert result.exit_code == 0
    assert log == result.output


@pytest.mark.datafiles(DATA_DIR)
def test_artifact_list_exact_contents_element(cli, datafiles):
    project = str(datafiles)

    # Ensure we have an artifact to read
    result = cli.run(project=project, args=['build', 'import-bin.bst'])
    assert result.exit_code == 0

    # List the contents via the element name
    result = cli.run(project=project, args=['artifact', 'list-contents', 'import-bin.bst'])
    assert result.exit_code == 0
    expected_output = ("import-bin.bst:\n"
                       "\tusr\n"
                       "\tusr/bin\n"
                       "\tusr/bin/hello\n\n")
    assert expected_output in result.output


@pytest.mark.datafiles(DATA_DIR)
def test_artifact_list_exact_contents_ref(cli, datafiles):
    project = str(datafiles)

    # Get the cache key of our test element
    key = cli.get_element_key(project, 'import-bin.bst')

    # Ensure we have an artifact to read
    result = cli.run(project=project, args=['build', 'import-bin.bst'])
    assert result.exit_code == 0

    # List the contents via the key
    result = cli.run(project=project, args=['artifact', 'list-contents', 'test/import-bin/' + key])
    assert result.exit_code == 0

    expected_output = ("test/import-bin/" + key + ":\n"
                       "\tusr\n"
                       "\tusr/bin\n"
                       "\tusr/bin/hello\n\n")
    assert expected_output in result.output


@pytest.mark.datafiles(DATA_DIR)
def test_artifact_list_exact_contents_glob(cli, datafiles):
    project = str(datafiles)

    # Ensure we have an artifact to read
    result = cli.run(project=project, args=['build', 'target.bst'])
    assert result.exit_code == 0

    # List the contents via glob
    result = cli.run(project=project, args=['artifact', 'list-contents', 'test/*'])
    assert result.exit_code == 0

    # get the cahe keys for each element in the glob
    import_bin_key = cli.get_element_key(project, 'import-bin.bst')
    import_dev_key = cli.get_element_key(project, 'import-dev.bst')
    compose_all_key = cli.get_element_key(project, 'compose-all.bst')
    target_key = cli.get_element_key(project, 'target.bst')

    expected_artifacts = ["test/import-bin/" + import_bin_key,
                          "test/import-dev/" + import_dev_key,
                          "test/compose-all/" + compose_all_key,
                          "test/target/" + target_key]

    for artifact in expected_artifacts:
        assert artifact in result.output


@pytest.mark.datafiles(DATA_DIR)
def test_artifact_log_files(cli, datafiles):
    project = str(datafiles)

    # Ensure we have an artifact to read
    result = cli.run(project=project, args=['build', 'target.bst'])
    assert result.exit_code == 0

    logfiles = os.path.join(project, "logfiles")
    target = os.path.join(project, logfiles, "target.log")
    import_bin = os.path.join(project, logfiles, "import-bin.log")
    # Ensure the logfile doesn't exist before the command is run
    assert not os.path.exists(logfiles)
    assert not os.path.exists(target)
    assert not os.path.exists(import_bin)

    # Run the command and ensure the file now exists
    result = cli.run(project=project, args=['artifact', 'log', '--out', logfiles, 'target.bst', 'import-bin.bst'])
    assert result.exit_code == 0
    assert os.path.exists(logfiles)
    assert os.path.exists(target)
    assert os.path.exists(import_bin)

    # Ensure the file contains the logs by checking for the LOG line
    with open(target, 'r') as f:
        data = f.read()
        assert "LOG     target.bst" in data
    with open(import_bin, 'r') as f:
        data = f.read()
        assert "LOG     import-bin.bst" in data


# Test that we can delete the artifact of the element which corresponds
# to the current project state
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_delete_element(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = 'target.bst'

    # Build the element and ensure it's cached
    result = cli.run(project=project, args=['build', element])
    result.assert_success()
    assert cli.get_element_state(project, element) == 'cached'

    result = cli.run(project=project, args=['artifact', 'delete', element])
    result.assert_success()
    assert cli.get_element_state(project, element) != 'cached'


# Test that we can delete an artifact by specifying its ref.
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_delete_artifact(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = 'target.bst'

    # Configure a local cache
    local_cache = os.path.join(str(tmpdir), 'cache')
    cli.configure({'cachedir': local_cache})

    # First build an element so that we can find its artifact
    result = cli.run(project=project, args=['build', element])
    result.assert_success()

    # Obtain the artifact ref
    cache_key = cli.get_element_key(project, element)
    artifact = os.path.join('test', os.path.splitext(element)[0], cache_key)

    # Explicitly check that the ARTIFACT exists in the cache
    assert os.path.exists(os.path.join(local_cache, 'artifacts', 'refs', artifact))

    # Delete the artifact
    result = cli.run(project=project, args=['artifact', 'delete', artifact])
    result.assert_success()

    # Check that the ARTIFACT is no longer in the cache
    assert not os.path.exists(os.path.join(local_cache, 'cas', 'refs', 'heads', artifact))


# Test the `bst artifact delete` command with multiple, different arguments.
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_delete_element_and_artifact(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = 'target.bst'
    dep = 'compose-all.bst'

    # Configure a local cache
    local_cache = os.path.join(str(tmpdir), 'cache')
    cli.configure({'cachedir': local_cache})

    # First build an element so that we can find its artifact
    result = cli.run(project=project, args=['build', element])
    result.assert_success()
    assert cli.get_element_states(project, [element, dep], deps="none") == {
        element: "cached",
        dep: "cached",
    }

    # Obtain the artifact ref
    cache_key = cli.get_element_key(project, element)
    artifact = os.path.join('test', os.path.splitext(element)[0], cache_key)

    # Explicitly check that the ARTIFACT exists in the cache
    assert os.path.exists(os.path.join(local_cache, 'artifacts', 'refs', artifact))

    # Delete the artifact
    result = cli.run(project=project, args=['artifact', 'delete', artifact, dep])
    result.assert_success()

    # Check that the ARTIFACT is no longer in the cache
    assert not os.path.exists(os.path.join(local_cache, 'artifacts', artifact))

    # Check that the dependency ELEMENT is no longer cached
    assert cli.get_element_state(project, dep) != 'cached'


# Test that we receive the appropriate stderr when we try to delete an artifact
# that is not present in the cache.
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_delete_unbuilt_artifact(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = 'target.bst'

    # delete it, just in case it's there
    _ = cli.run(project=project, args=['artifact', 'delete', element])

    # Ensure the element is not cached
    assert cli.get_element_state(project, element) != 'cached'

    # Now try and remove it again (now we know its not there)
    result = cli.run(project=project, args=['artifact', 'delete', element])

    cache_key = cli.get_element_key(project, element)
    artifact = os.path.join('test', os.path.splitext(element)[0], cache_key)
    expected_err = "WARNING Could not find ref '{}'".format(artifact)
    assert expected_err in result.stderr


# Test that an artifact pulled from it's remote cache (without it's buildtree) will not
# throw an Exception when trying to prune the cache.
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_delete_pulled_artifact_without_buildtree(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = 'target.bst'

    # Set up remote and local shares
    local_cache = os.path.join(str(tmpdir), 'artifacts')
    with create_artifact_share(os.path.join(str(tmpdir), 'remote')) as remote:
        cli.configure({
            'artifacts': {'url': remote.repo, 'push': True},
            'cachedir': local_cache,
        })

        # Build the element
        result = cli.run(project=project, args=['build', element])
        result.assert_success()

        # Make sure it's in the share
        assert remote.has_artifact(cli.get_artifact_name(project, 'test', element))

        # Delete and then pull the artifact (without its buildtree)
        result = cli.run(project=project, args=['artifact', 'delete', element])
        result.assert_success()
        assert cli.get_element_state(project, element) != 'cached'
        result = cli.run(project=project, args=['artifact', 'pull', element])
        result.assert_success()
        assert cli.get_element_state(project, element) == 'cached'

        # Now delete it again (it should have been pulled without the buildtree, but
        # a digest of the buildtree is pointed to in the artifact's metadata
        result = cli.run(project=project, args=['artifact', 'delete', element])
        result.assert_success()
        assert cli.get_element_state(project, element) != 'cached'


# Test that we can delete the build deps of an element
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_delete_elements_build_deps(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = 'target.bst'

    # Build the element and ensure it's cached
    result = cli.run(project=project, args=['build', element])
    result.assert_success()

    # Assert element and build deps are cached
    assert cli.get_element_state(project, element) == 'cached'
    bdep_states = cli.get_element_states(project, [element], deps='build')
    for state in bdep_states.values():
        assert state == 'cached'

    result = cli.run(project=project, args=['artifact', 'delete', '--deps', 'build', element])
    result.assert_success()

    # Assert that the build deps have been deleted and that the artifact remains cached
    assert cli.get_element_state(project, element) == 'cached'
    bdep_states = cli.get_element_states(project, [element], deps='build')
    for state in bdep_states.values():
        assert state != 'cached'


# Test that we can delete the build deps of an artifact by providing an artifact ref
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_delete_artifacts_build_deps(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = 'target.bst'

    # Configure a local cache
    local_cache = os.path.join(str(tmpdir), 'cache')
    cli.configure({'cachedir': local_cache})

    # First build an element so that we can find its artifact
    result = cli.run(project=project, args=['build', element])
    result.assert_success()

    # Obtain the artifact ref
    cache_key = cli.get_element_key(project, element)
    artifact = os.path.join('test', os.path.splitext(element)[0], cache_key)

    # Explicitly check that the ARTIFACT exists in the cache
    assert os.path.exists(os.path.join(local_cache, 'artifacts', 'refs', artifact))

    # get the artifact refs of the build dependencies
    bdep_refs = []
    bdep_states = cli.get_element_states(project, [element], deps='build')
    for bdep in bdep_states.keys():
        bdep_refs.append(os.path.join('test', _get_normal_name(bdep), cli.get_element_key(project, bdep)))

    # Assert build dependencies are cached
    for ref in bdep_refs:
        assert os.path.exists(os.path.join(local_cache, 'artifacts', 'refs', ref))

    # Delete the artifact
    result = cli.run(project=project, args=['artifact', 'delete', '--deps', 'build', artifact])
    result.assert_success()

    # Check that the artifact's build deps are no longer in the cache
    # Assert build dependencies have been deleted and that the artifact remains
    for ref in bdep_refs:
        assert not os.path.exists(os.path.join(local_cache, 'artifacts', 'refs', ref))
    assert os.path.exists(os.path.join(local_cache, 'artifacts', 'refs', artifact))


# Test that `--deps all` option fails if an artifact ref is specified
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_delete_artifact_with_deps_all_fails(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = 'target.bst'

    # First build an element so that we can find its artifact
    result = cli.run(project=project, args=['build', element])
    result.assert_success()

    # Obtain the artifact ref
    cache_key = cli.get_element_key(project, element)
    artifact = os.path.join('test', os.path.splitext(element)[0], cache_key)

    # Try to delete the artifact with all of its dependencies
    result = cli.run(project=project, args=['artifact', 'delete', '--deps', 'all', artifact])
    result.assert_main_error(ErrorDomain.STREAM, None)

    assert "Error: '--deps all' is not supported for artifact refs" in result.stderr


# Test artifact show
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_show_element_name(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = 'target.bst'

    result = cli.run(project=project, args=['artifact', 'show', element])
    result.assert_success()
    assert 'not cached {}'.format(element) in result.output

    result = cli.run(project=project, args=['build', element])
    result.assert_success()

    result = cli.run(project=project, args=['artifact', 'show', element])
    result.assert_success()
    assert 'cached {}'.format(element) in result.output


# Test artifact show on a failed element
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_show_failed_element(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = 'manual.bst'

    result = cli.run(project=project, args=['artifact', 'show', element])
    result.assert_success()
    assert 'not cached {}'.format(element) in result.output

    result = cli.run(project=project, args=['build', element])
    result.assert_task_error(ErrorDomain.SANDBOX, 'missing-command')

    result = cli.run(project=project, args=['artifact', 'show', element])
    result.assert_success()
    assert 'failed {}'.format(element) in result.output


# Test artifact show with a deleted dependency
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_show_element_missing_deps(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = 'target.bst'
    dependency = 'import-bin.bst'

    result = cli.run(project=project, args=['build', element])
    result.assert_success()

    result = cli.run(project=project, args=['artifact', 'delete', dependency])
    result.assert_success()

    result = cli.run(project=project, args=['artifact', 'show', '--deps', 'all', element])
    result.assert_success()
    assert 'not cached {}'.format(dependency) in result.output
    assert 'cached {}'.format(element) in result.output


# Test artifact show with artifact ref
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_show_artifact_ref(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = 'target.bst'

    result = cli.run(project=project, args=['build', element])
    result.assert_success()

    cache_key = cli.get_element_key(project, element)
    artifact_ref = 'test/target/' + cache_key

    result = cli.run(project=project, args=['artifact', 'show', artifact_ref])
    result.assert_success()
    assert 'cached {}'.format(artifact_ref) in result.output


# Test artifact show artifact in remote
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_show_element_available_remotely(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = 'target.bst'

    # Set up remote and local shares
    local_cache = os.path.join(str(tmpdir), 'artifacts')
    with create_artifact_share(os.path.join(str(tmpdir), 'remote')) as remote:
        cli.configure({
            'artifacts': {'url': remote.repo, 'push': True},
            'cachedir': local_cache,
        })

        # Build the element
        result = cli.run(project=project, args=['build', element])
        result.assert_success()

        # Make sure it's in the share
        assert remote.has_artifact(cli.get_artifact_name(project, 'test', element))

        # Delete the artifact from the local cache
        result = cli.run(project=project, args=['artifact', 'delete', element])
        result.assert_success()
        assert cli.get_element_state(project, element) != 'cached'

        result = cli.run(project=project, args=['artifact', 'show', element])
        result.assert_success()
        assert 'available {}'.format(element) in result.output
