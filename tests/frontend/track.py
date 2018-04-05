import os
import pytest
from tests.testutils import cli, create_repo, ALL_REPO_KINDS

from buildstream._exceptions import ErrorDomain
from buildstream import _yaml

from . import configure_project

# Project directory
TOP_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TOP_DIR, 'project')


def generate_element(repo, element_path, dep_name=None):
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config()
        ]
    }
    if dep_name:
        element['depends'] = [dep_name]

    _yaml.dump(element, element_path)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", [('inline'), ('project.refs')])
@pytest.mark.parametrize("kind", [(kind) for kind in ALL_REPO_KINDS])
def test_track(cli, tmpdir, datafiles, ref_storage, kind):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    dev_files_path = os.path.join(project, 'files', 'dev-files')
    element_path = os.path.join(project, 'elements')
    element_name = 'track-test-{}.bst'.format(kind)

    configure_project(project, {
        'ref-storage': ref_storage
    })

    # Create our repo object of the given source type with
    # the dev files, and then collect the initial ref.
    #
    repo = create_repo(kind, str(tmpdir))
    ref = repo.create(dev_files_path)

    # Generate the element
    generate_element(repo, os.path.join(element_path, element_name))

    # Assert that a fetch is needed
    assert cli.get_element_state(project, element_name) == 'no reference'

    # Now first try to track it
    result = cli.run(project=project, args=['track', element_name])
    result.assert_success()

    # And now fetch it: The Source has probably already cached the
    # latest ref locally, but it is not required to have cached
    # the associated content of the latest ref at track time, that
    # is the job of fetch.
    result = cli.run(project=project, args=['fetch', element_name])
    result.assert_success()

    # Assert that we are now buildable because the source is
    # now cached.
    assert cli.get_element_state(project, element_name) == 'buildable'

    # Assert there was a project.refs created, depending on the configuration
    if ref_storage == 'project.refs':
        assert os.path.exists(os.path.join(project, 'project.refs'))
    else:
        assert not os.path.exists(os.path.join(project, 'project.refs'))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", [(kind) for kind in ALL_REPO_KINDS])
def test_track_recurse(cli, tmpdir, datafiles, kind):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    dev_files_path = os.path.join(project, 'files', 'dev-files')
    element_path = os.path.join(project, 'elements')
    element_dep_name = 'track-test-dep-{}.bst'.format(kind)
    element_target_name = 'track-test-target-{}.bst'.format(kind)

    # Create our repo object of the given source type with
    # the dev files, and then collect the initial ref.
    #
    repo = create_repo(kind, str(tmpdir))
    ref = repo.create(dev_files_path)

    # Write out our test targets
    generate_element(repo, os.path.join(element_path, element_dep_name))
    generate_element(repo, os.path.join(element_path, element_target_name),
                     dep_name=element_dep_name)

    # Assert that a fetch is needed
    assert cli.get_element_state(project, element_dep_name) == 'no reference'
    assert cli.get_element_state(project, element_target_name) == 'no reference'

    # Now first try to track it
    result = cli.run(project=project, args=[
        'track', '--deps', 'all',
        element_target_name])
    result.assert_success()

    # And now fetch it: The Source has probably already cached the
    # latest ref locally, but it is not required to have cached
    # the associated content of the latest ref at track time, that
    # is the job of fetch.
    result = cli.run(project=project, args=[
        'fetch', '--deps', 'all',
        element_target_name])
    result.assert_success()

    # Assert that the dependency is buildable and the target is waiting
    assert cli.get_element_state(project, element_dep_name) == 'buildable'
    assert cli.get_element_state(project, element_target_name) == 'waiting'


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", [(kind) for kind in ALL_REPO_KINDS])
def test_track_recurse_except(cli, tmpdir, datafiles, kind):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    dev_files_path = os.path.join(project, 'files', 'dev-files')
    element_path = os.path.join(project, 'elements')
    element_dep_name = 'track-test-dep-{}.bst'.format(kind)
    element_target_name = 'track-test-target-{}.bst'.format(kind)

    # Create our repo object of the given source type with
    # the dev files, and then collect the initial ref.
    #
    repo = create_repo(kind, str(tmpdir))
    ref = repo.create(dev_files_path)

    # Write out our test targets
    generate_element(repo, os.path.join(element_path, element_dep_name))
    generate_element(repo, os.path.join(element_path, element_target_name),
                     dep_name=element_dep_name)

    # Assert that a fetch is needed
    assert cli.get_element_state(project, element_dep_name) == 'no reference'
    assert cli.get_element_state(project, element_target_name) == 'no reference'

    # Now first try to track it
    result = cli.run(project=project, args=[
        'track', '--deps', 'all', '--except', element_dep_name,
        element_target_name])
    result.assert_success()

    # And now fetch it: The Source has probably already cached the
    # latest ref locally, but it is not required to have cached
    # the associated content of the latest ref at track time, that
    # is the job of fetch.
    result = cli.run(project=project, args=[
        'fetch', '--deps', 'none',
        element_target_name])
    result.assert_success()

    # Assert that the dependency is buildable and the target is waiting
    assert cli.get_element_state(project, element_dep_name) == 'no reference'
    assert cli.get_element_state(project, element_target_name) == 'waiting'


@pytest.mark.datafiles(os.path.join(TOP_DIR))
@pytest.mark.parametrize("ref_storage", [('inline'), ('project-refs')])
def test_track_optional(cli, tmpdir, datafiles, ref_storage):
    project = os.path.join(datafiles.dirname, datafiles.basename, 'track-optional-' + ref_storage)
    dev_files_path = os.path.join(project, 'files')
    element_path = os.path.join(project, 'target.bst')

    # Create our repo object of the given source type with
    # the dev files, and then collect the initial ref.
    #
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(dev_files_path)

    # Now create an optional test branch and add a commit to that,
    # so two branches with different heads now exist.
    #
    repo.branch('test')
    repo.add_commit()

    # Substitute the {repo} for the git repo we created
    with open(element_path) as f:
        target_bst = f.read()
    target_bst = target_bst.format(repo=repo.repo)
    with open(element_path, 'w') as f:
        f.write(target_bst)

    # First track for both options
    #
    # We want to track and persist the ref separately in this test
    #
    result = cli.run(project=project, args=['--option', 'test', 'False', 'track', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['--option', 'test', 'True', 'track', 'target.bst'])
    result.assert_success()

    # Now fetch the key for both options
    #
    result = cli.run(project=project, args=[
        '--option', 'test', 'False', 'show', '--deps', 'none', '--format', '%{key}', 'target.bst'
    ])
    result.assert_success()
    master_key = result.output

    result = cli.run(project=project, args=[
        '--option', 'test', 'True', 'show', '--deps', 'none', '--format', '%{key}', 'target.bst'
    ])
    result.assert_success()
    test_key = result.output

    # Assert that the keys are different when having
    # tracked separate branches
    assert test_key != master_key


@pytest.mark.datafiles(os.path.join(TOP_DIR, 'track-cross-junction'))
@pytest.mark.parametrize("ref_storage", [('inline'), ('project.refs')])
def test_track_cross_junction(cli, tmpdir, datafiles, ref_storage):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    dev_files_path = os.path.join(project, 'files')
    target_path = os.path.join(project, 'target.bst')
    subtarget_path = os.path.join(project, 'subproject', 'subtarget.bst')

    # Create our repo object of the given source type with
    # the dev files, and then collect the initial ref.
    #
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(dev_files_path)

    # Generate two elements using the git source, one in
    # the main project and one in the subproject.
    generate_element(repo, target_path, dep_name='subproject.bst')
    generate_element(repo, subtarget_path)

    # Generate project.conf
    #
    project_conf = {
        'name': 'test',
        'ref-storage': ref_storage
    }
    _yaml.dump(project_conf, os.path.join(project, 'project.conf'))

    #
    # FIXME: This can be simplified when we have support
    #        for addressing of junctioned elements.
    #
    def get_subproject_element_state():
        result = cli.run(project=project, args=[
            'show', '--deps', 'all',
            '--format', '%{name}|%{state}', 'target.bst'
        ])
        result.assert_success()

        # Create two dimentional list of the result,
        # first line should be the junctioned element
        lines = [
            line.split('|')
            for line in result.output.splitlines()
        ]
        assert lines[0][0] == 'subproject-junction.bst:subtarget.bst'
        return lines[0][1]

    #
    # Assert that we have no reference yet for the cross junction element
    #
    assert get_subproject_element_state() == 'no reference'

    # Track recursively across the junction
    result = cli.run(project=project, args=['track', '--deps', 'all', 'target.bst'])

    if ref_storage == 'inline':
        #
        # Cross junction tracking is not allowed when the toplevel project
        # is using inline ref storage.
        #
        result.assert_main_error(ErrorDomain.PIPELINE, 'untrackable-sources')
    else:
        #
        # Tracking is allowed with project.refs ref storage
        #
        result.assert_success()

        #
        # Assert that we now have a ref for the subproject element
        #
        assert get_subproject_element_state() == 'buildable'


@pytest.mark.datafiles(os.path.join(TOP_DIR, 'consistencyerror'))
def test_track_consistency_error(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # Track the element causing a consistency error
    result = cli.run(project=project, args=['track', 'error.bst'])
    result.assert_main_error(ErrorDomain.PIPELINE, None)
    result.assert_task_error(ErrorDomain.SOURCE, 'the-consistency-error')


@pytest.mark.datafiles(os.path.join(TOP_DIR, 'consistencyerror'))
def test_track_consistency_bug(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # Track the element causing an unhandled exception
    result = cli.run(project=project, args=['track', 'bug.bst'])

    # We expect BuildStream to fail gracefully, with no recorded exception.
    result.assert_main_error(ErrorDomain.PIPELINE, None)
