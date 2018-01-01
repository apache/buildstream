import os
import pytest
import shutil
from tests.testutils import cli, create_repo, ALL_REPO_KINDS

from buildstream import _yaml

repo_kinds = [(kind) for kind in ALL_REPO_KINDS]

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


def open_workspace(cli, tmpdir, datafiles, kind, track):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    bin_files_path = os.path.join(project, 'files', 'bin-files')
    element_path = os.path.join(project, 'elements')
    element_name = 'workspace-test-{}.bst'.format(kind)
    workspace = os.path.join(str(tmpdir), 'workspace')

    # Create our repo object of the given source type with
    # the bin files, and then collect the initial ref.
    #
    repo = create_repo(kind, str(tmpdir))
    ref = repo.create(bin_files_path)
    if track:
        ref = None

    # Write out our test target
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config(ref=ref)
        ]
    }
    _yaml.dump(element,
               os.path.join(element_path,
                            element_name))

    # Assert that there is no reference, a track & fetch is needed
    state = cli.get_element_state(project, element_name)
    if track:
        assert state == 'no reference'
    else:
        assert state == 'fetch needed'

    # Now open the workspace, this should have the effect of automatically
    # tracking & fetching the source from the repo.
    args = ['workspace', 'open']
    if track:
        args.append('--track')
    args.extend([element_name, workspace])

    result = cli.run(project=project, args=args)
    result.assert_success()

    # Assert that we are now buildable because the source is
    # now cached.
    assert cli.get_element_state(project, element_name) == 'buildable'

    # Check that the executable hello file is found in the workspace
    filename = os.path.join(workspace, 'usr', 'bin', 'hello')
    assert os.path.exists(filename)

    return (element_name, project, workspace)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", repo_kinds)
def test_open(cli, tmpdir, datafiles, kind):
    open_workspace(cli, tmpdir, datafiles, kind, False)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", repo_kinds)
def test_open_track(cli, tmpdir, datafiles, kind):
    open_workspace(cli, tmpdir, datafiles, kind, True)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", repo_kinds)
def test_close(cli, tmpdir, datafiles, kind):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, kind, False)

    # Now open the workspace, this should have the
    # effect of automatically fetching the source from the repo.
    result = cli.run(project=project, args=[
        'workspace', 'close', '--remove-dir', element_name
    ])
    result.assert_success()

    # Assert the workspace dir has been deleted
    assert not os.path.exists(workspace)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", repo_kinds)
def test_close_removed(cli, tmpdir, datafiles, kind):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, kind, False)

    # Remove it first, closing the workspace should work
    shutil.rmtree(workspace)

    # Now open the workspace, this should have the
    # effect of automatically fetching the source from the repo.
    result = cli.run(project=project, args=[
        'workspace', 'close', element_name
    ])
    result.assert_success()

    # Assert the workspace dir has been deleted
    assert not os.path.exists(workspace)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", repo_kinds)
def test_reset(cli, tmpdir, datafiles, kind):
    # Open the workspace
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, kind, False)

    # Modify workspace
    shutil.rmtree(os.path.join(workspace, 'usr', 'bin'))
    os.makedirs(os.path.join(workspace, 'etc'))
    with open(os.path.join(workspace, 'etc', 'pony.conf'), 'w') as f:
        f.write("PONY='pink'")

    # Now reset the open workspace, this should have the
    # effect of reverting our changes.
    result = cli.run(project=project, args=[
        'workspace', 'reset', element_name
    ])
    result.assert_success()
    assert os.path.exists(os.path.join(workspace, 'usr', 'bin', 'hello'))
    assert not os.path.exists(os.path.join(workspace, 'etc', 'pony.conf'))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", repo_kinds)
def test_list(cli, tmpdir, datafiles, kind):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, kind, False)

    # Now reset the open workspace, this should have the
    # effect of reverting our changes.
    result = cli.run(project=project, args=[
        'workspace', 'list'
    ])
    result.assert_success()

    loaded = _yaml.load_data(result.output)
    assert isinstance(loaded.get('workspaces'), list)
    workspaces = loaded['workspaces']
    assert len(workspaces) == 1

    space = workspaces[0]
    assert space['element'] == element_name
    assert space['directory'] == workspace


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", repo_kinds)
def test_build(cli, tmpdir, datafiles, kind):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, kind, False)
    checkout = os.path.join(str(tmpdir), 'checkout')

    # Modify workspace
    shutil.rmtree(os.path.join(workspace, 'usr', 'bin'))
    os.makedirs(os.path.join(workspace, 'etc'))
    with open(os.path.join(workspace, 'etc', 'pony.conf'), 'w') as f:
        f.write("PONY='pink'")

    # Build modified workspace
    assert cli.get_element_state(project, element_name) == 'buildable'
    result = cli.run(project=project, args=['build', element_name])
    result.assert_success()
    assert cli.get_element_state(project, element_name) == 'cached'

    # Checkout the result
    result = cli.run(project=project, args=[
        'checkout', element_name, checkout
    ])
    result.assert_success()

    # Check that the pony.conf from the modified workspace exists
    filename = os.path.join(checkout, 'etc', 'pony.conf')
    assert os.path.exists(filename)

    # Check that the original /usr/bin/hello is not in the checkout
    assert not os.path.exists(os.path.join(workspace, 'usr', 'bin', 'hello'))
