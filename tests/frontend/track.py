import stat
import os
import pytest
from tests.testutils import cli, create_repo, ALL_REPO_KINDS, generate_junction

from buildstream._exceptions import ErrorDomain, LoadErrorReason
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
def test_track_single(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    dev_files_path = os.path.join(project, 'files', 'dev-files')
    element_path = os.path.join(project, 'elements')
    element_dep_name = 'track-test-dep.bst'
    element_target_name = 'track-test-target.bst'

    # Create our repo object of the given source type with
    # the dev files, and then collect the initial ref.
    #
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(dev_files_path)

    # Write out our test targets
    generate_element(repo, os.path.join(element_path, element_dep_name))
    generate_element(repo, os.path.join(element_path, element_target_name),
                     dep_name=element_dep_name)

    # Assert that tracking is needed for both elements
    assert cli.get_element_state(project, element_dep_name) == 'no reference'
    assert cli.get_element_state(project, element_target_name) == 'no reference'

    # Now first try to track only one element
    result = cli.run(project=project, args=[
        'track', '--deps', 'none',
        element_target_name])
    result.assert_success()

    # And now fetch it
    result = cli.run(project=project, args=[
        'fetch', '--deps', 'none',
        element_target_name])
    result.assert_success()

    # Assert that the dependency is waiting and the target has still never been tracked
    assert cli.get_element_state(project, element_dep_name) == 'no reference'
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
@pytest.mark.parametrize("cross_junction", [('cross'), ('nocross')])
@pytest.mark.parametrize("ref_storage", [('inline'), ('project.refs')])
def test_track_cross_junction(cli, tmpdir, datafiles, cross_junction, ref_storage):
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
    args = ['track', '--deps', 'all']
    if cross_junction == 'cross':
        args += ['--cross-junctions']
    args += ['target.bst']

    result = cli.run(project=project, args=args)

    if ref_storage == 'inline':

        if cross_junction == 'cross':
            #
            # Cross junction tracking is not allowed when the toplevel project
            # is using inline ref storage.
            #
            result.assert_main_error(ErrorDomain.PIPELINE, 'untrackable-sources')
        else:
            #
            # No cross juction tracking was requested
            #
            result.assert_success()
            assert get_subproject_element_state() == 'no reference'
    else:
        #
        # Tracking is allowed with project.refs ref storage
        #
        result.assert_success()

        #
        # If cross junction tracking was enabled, we should now be buildable
        #
        if cross_junction == 'cross':
            assert get_subproject_element_state() == 'buildable'
        else:
            assert get_subproject_element_state() == 'no reference'


@pytest.mark.datafiles(os.path.join(TOP_DIR, 'consistencyerror'))
def test_track_consistency_error(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # Track the element causing a consistency error
    result = cli.run(project=project, args=['track', 'error.bst'])
    result.assert_main_error(ErrorDomain.STREAM, None)
    result.assert_task_error(ErrorDomain.SOURCE, 'the-consistency-error')


@pytest.mark.datafiles(os.path.join(TOP_DIR, 'consistencyerror'))
def test_track_consistency_bug(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # Track the element causing an unhandled exception
    result = cli.run(project=project, args=['track', 'bug.bst'])

    # We expect BuildStream to fail gracefully, with no recorded exception.
    result.assert_main_error(ErrorDomain.STREAM, None)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", [('inline'), ('project.refs')])
def test_inconsistent_junction(cli, tmpdir, datafiles, ref_storage):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    subproject_path = os.path.join(project, 'files', 'sub-project')
    junction_path = os.path.join(project, 'elements', 'junction.bst')
    element_path = os.path.join(project, 'elements', 'junction-dep.bst')

    configure_project(project, {
        'ref-storage': ref_storage
    })

    # Create a repo to hold the subproject and generate a junction element for it
    generate_junction(tmpdir, subproject_path, junction_path, store_ref=False)

    # Create a stack element to depend on a cross junction element
    #
    element = {
        'kind': 'stack',
        'depends': [
            {
                'junction': 'junction.bst',
                'filename': 'import-etc.bst'
            }
        ]
    }
    _yaml.dump(element, element_path)

    # Now try to track it, this will bail with the appropriate error
    # informing the user to track the junction first
    result = cli.run(project=project, args=['track', 'junction-dep.bst'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.SUBPROJECT_INCONSISTENT)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", [('inline'), ('project.refs')])
def test_junction_element(cli, tmpdir, datafiles, ref_storage):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    subproject_path = os.path.join(project, 'files', 'sub-project')
    junction_path = os.path.join(project, 'elements', 'junction.bst')
    element_path = os.path.join(project, 'elements', 'junction-dep.bst')

    configure_project(project, {
        'ref-storage': ref_storage
    })

    # Create a repo to hold the subproject and generate a junction element for it
    generate_junction(tmpdir, subproject_path, junction_path, store_ref=False)

    # Create a stack element to depend on a cross junction element
    #
    element = {
        'kind': 'stack',
        'depends': [
            {
                'junction': 'junction.bst',
                'filename': 'import-etc.bst'
            }
        ]
    }
    _yaml.dump(element, element_path)

    # First demonstrate that showing the pipeline yields an error
    result = cli.run(project=project, args=['show', 'junction-dep.bst'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.SUBPROJECT_INCONSISTENT)

    # Now track the junction itself
    result = cli.run(project=project, args=['track', 'junction.bst'])
    result.assert_success()

    # Now assert element state (via bst show under the hood) of the dep again
    assert cli.get_element_state(project, 'junction-dep.bst') == 'waiting'


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", [('inline'), ('project.refs')])
@pytest.mark.parametrize("kind", [(kind) for kind in ALL_REPO_KINDS])
def test_cross_junction(cli, tmpdir, datafiles, ref_storage, kind):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    subproject_path = os.path.join(project, 'files', 'sub-project')
    junction_path = os.path.join(project, 'elements', 'junction.bst')
    etc_files = os.path.join(subproject_path, 'files', 'etc-files')
    repo_element_path = os.path.join(subproject_path, 'elements',
                                     'import-etc-repo.bst')

    configure_project(project, {
        'ref-storage': ref_storage
    })

    repo = create_repo(kind, str(tmpdir.join('element_repo')))
    ref = repo.create(etc_files)

    generate_element(repo, repo_element_path)

    generate_junction(str(tmpdir.join('junction_repo')),
                      subproject_path, junction_path, store_ref=False)

    # Track the junction itself first.
    result = cli.run(project=project, args=['track', 'junction.bst'])
    result.assert_success()

    assert cli.get_element_state(project, 'junction.bst:import-etc-repo.bst') == 'no reference'

    # Track the cross junction element. -J is not given, it is implied.
    result = cli.run(project=project, args=['track', 'junction.bst:import-etc-repo.bst'])

    if ref_storage == 'inline':
        # This is not allowed to track cross junction without project.refs.
        result.assert_main_error(ErrorDomain.PIPELINE, 'untrackable-sources')
    else:
        result.assert_success()

        assert cli.get_element_state(project, 'junction.bst:import-etc-repo.bst') == 'buildable'

        assert os.path.exists(os.path.join(project, 'project.refs'))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", [('inline'), ('project.refs')])
@pytest.mark.parametrize("kind", [(kind) for kind in ALL_REPO_KINDS])
def test_track_include(cli, tmpdir, datafiles, ref_storage, kind):
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
    element = {
        'kind': 'import',
        '(@)': ['elements/sources.yml']
    }
    sources = {
        'sources': [
            repo.source_config()
        ]
    }

    _yaml.dump(element, os.path.join(element_path, element_name))
    _yaml.dump(sources, os.path.join(element_path, 'sources.yml'))

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
        new_sources = _yaml.load(os.path.join(element_path, 'sources.yml'))
        assert 'sources' in new_sources
        assert len(new_sources['sources']) == 1
        assert 'ref' in new_sources['sources'][0]
        assert ref == new_sources['sources'][0]['ref']


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", [('inline'), ('project.refs')])
@pytest.mark.parametrize("kind", [(kind) for kind in ALL_REPO_KINDS])
def test_track_include_junction(cli, tmpdir, datafiles, ref_storage, kind):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    dev_files_path = os.path.join(project, 'files', 'dev-files')
    element_path = os.path.join(project, 'elements')
    element_name = 'track-test-{}.bst'.format(kind)
    subproject_path = os.path.join(project, 'files', 'sub-project')
    sub_element_path = os.path.join(subproject_path, 'elements')
    junction_path = os.path.join(element_path, 'junction.bst')

    configure_project(project, {
        'ref-storage': ref_storage
    })

    # Create our repo object of the given source type with
    # the dev files, and then collect the initial ref.
    #
    repo = create_repo(kind, str(tmpdir.join('element_repo')))
    ref = repo.create(dev_files_path)

    # Generate the element
    element = {
        'kind': 'import',
        '(@)': ['junction.bst:elements/sources.yml']
    }
    sources = {
        'sources': [
            repo.source_config()
        ]
    }

    _yaml.dump(element, os.path.join(element_path, element_name))
    _yaml.dump(sources, os.path.join(sub_element_path, 'sources.yml'))

    generate_junction(str(tmpdir.join('junction_repo')),
                      subproject_path, junction_path, store_ref=True)

    result = cli.run(project=project, args=['track', 'junction.bst'])
    result.assert_success()

    # Assert that a fetch is needed
    assert cli.get_element_state(project, element_name) == 'no reference'

    # Now first try to track it
    result = cli.run(project=project, args=['track', element_name])

    # Assert there was a project.refs created, depending on the configuration
    if ref_storage == 'inline':
        # FIXME: We should expect an error. But only a warning is emitted
        # result.assert_main_error(ErrorDomain.SOURCE, 'tracking-junction-fragment')

        assert 'junction.bst:elements/sources.yml: Cannot track source in a fragment from a junction' in result.stderr
    else:
        assert os.path.exists(os.path.join(project, 'project.refs'))

        # And now fetch it: The Source has probably already cached the
        # latest ref locally, but it is not required to have cached
        # the associated content of the latest ref at track time, that
        # is the job of fetch.
        result = cli.run(project=project, args=['fetch', element_name])
        result.assert_success()

        # Assert that we are now buildable because the source is
        # now cached.
        assert cli.get_element_state(project, element_name) == 'buildable'


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", [('inline'), ('project.refs')])
@pytest.mark.parametrize("kind", [(kind) for kind in ALL_REPO_KINDS])
def test_track_junction_included(cli, tmpdir, datafiles, ref_storage, kind):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_path = os.path.join(project, 'elements')
    subproject_path = os.path.join(project, 'files', 'sub-project')
    sub_element_path = os.path.join(subproject_path, 'elements')
    junction_path = os.path.join(element_path, 'junction.bst')

    configure_project(project, {
        'ref-storage': ref_storage,
        '(@)': ['junction.bst:test.yml']
    })

    generate_junction(str(tmpdir.join('junction_repo')),
                      subproject_path, junction_path, store_ref=False)

    result = cli.run(project=project, args=['track', 'junction.bst'])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", [(kind) for kind in ALL_REPO_KINDS])
def test_track_error_cannot_write_file(cli, tmpdir, datafiles, kind):
    if os.geteuid() == 0:
        pytest.skip("This is not testable with root permissions")

    project = str(datafiles)
    dev_files_path = os.path.join(project, 'files', 'dev-files')
    element_path = os.path.join(project, 'elements')
    element_name = 'track-test-{}.bst'.format(kind)

    configure_project(project, {
        'ref-storage': 'inline'
    })

    repo = create_repo(kind, str(tmpdir))
    ref = repo.create(dev_files_path)

    element_full_path = os.path.join(element_path, element_name)
    generate_element(repo, element_full_path)

    st = os.stat(element_path)
    try:
        read_mask = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
        os.chmod(element_path, stat.S_IMODE(st.st_mode) & ~read_mask)

        result = cli.run(project=project, args=['track', element_name])
        result.assert_main_error(ErrorDomain.STREAM, None)
        result.assert_task_error(ErrorDomain.SOURCE, 'save-ref-error')
    finally:
        os.chmod(element_path, stat.S_IMODE(st.st_mode))
