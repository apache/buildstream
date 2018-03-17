import os
import pytest
from tests.testutils import cli, create_repo, ALL_REPO_KINDS

from buildstream import _yaml

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


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


def configure_project(path, config):
    config['name'] = 'test'
    config['element-path'] = 'elements'
    _yaml.dump(config, os.path.join(path, 'project.conf'))


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
