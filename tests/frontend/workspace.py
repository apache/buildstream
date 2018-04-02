import os
import pytest
import shutil
import subprocess
from ruamel.yaml.comments import CommentedSet
from tests.testutils import cli, create_repo, ALL_REPO_KINDS

from buildstream import _yaml
from buildstream._exceptions import ErrorDomain, LoadError, LoadErrorReason

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
def test_open_bzr(cli, tmpdir, datafiles):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, "bzr", False)

    # Check that the .bzr dir exists
    bzrdir = os.path.join(workspace, ".bzr")
    assert(os.path.isdir(bzrdir))

    # Check that the correct origin branch is set
    element_config = _yaml.load(os.path.join(project, "elements", element_name))
    source_config = element_config['sources'][0]
    output = subprocess.check_output(["bzr", "info"], cwd=workspace)
    stripped_url = source_config['url'].lstrip("file:///")
    expected_output_str = ("checkout of branch: /{}/{}"
                           .format(stripped_url, source_config['track']))
    assert(expected_output_str in str(output))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", repo_kinds)
def test_open_track(cli, tmpdir, datafiles, kind):
    open_workspace(cli, tmpdir, datafiles, kind, True)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", repo_kinds)
def test_close(cli, tmpdir, datafiles, kind):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, kind, False)

    # Close the workspace
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

    # Close the workspace
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

    # Now list the workspaces
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
    assert cli.get_element_key(project, element_name) == "{:?<64}".format('')
    result = cli.run(project=project, args=['build', element_name])
    result.assert_success()
    assert cli.get_element_state(project, element_name) == 'cached'
    assert cli.get_element_key(project, element_name) != "{:?<64}".format('')

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


# Ensure that various versions that should not be accepted raise a
# LoadError.INVALID_DATA
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("workspace_cfg", [
    # Test loading a negative workspace version
    {"format-version": -1},
    # Test loading version 0 with two sources
    {
        "format-version": 0,
        "alpha.bst": {
            0: "/workspaces/bravo",
            1: "/workspaces/charlie",
        }
    },
    # Test loading a version with decimals
    {"format-version": 0.5},
    # Test loading a future version
    {"format-version": 3}
])
def test_list_unsupported_workspace(cli, tmpdir, datafiles, workspace_cfg):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    bin_files_path = os.path.join(project, 'files', 'bin-files')
    element_path = os.path.join(project, 'elements')
    element_name = 'workspace-version.bst'
    os.makedirs(os.path.join(project, '.bst'))
    workspace_config_path = os.path.join(project, '.bst', 'workspaces.yml')

    _yaml.dump(workspace_cfg, workspace_config_path)

    result = cli.run(project=project, args=['workspace', 'list'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


# Ensure that various versions that should be accepted are parsed
# correctly.
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("workspace_cfg,expected", [
    # Test loading version 0 without a dict
    ({
        "alpha.bst": "/workspaces/bravo"
    }, {
        "format-version": 2,
        "workspaces": {
            "alpha.bst": {
                "path": "/workspaces/bravo",
                "running_files": {}
            }
        }
    }),
    # Test loading version 0 with only one source
    ({
        "alpha.bst": {
            0: "/workspaces/bravo"
        }
    }, {
        "format-version": 2,
        "workspaces": {
            "alpha.bst": {
                "path": "/workspaces/bravo",
                "running_files": {}
            }
        }
    }),
    # Test loading version 1
    ({
        "format-version": 1,
        "workspaces": {
            "alpha.bst": {
                "path": "/workspaces/bravo"
            }
        }
    }, {
        "format-version": 2,
        "workspaces": {
            "alpha.bst": {
                "path": "/workspaces/bravo",
                "running_files": {}
            }
        }
    }),
    # Test loading version 2
    ({
        "format-version": 2,
        "workspaces": {
            "alpha.bst": {
                "path": "/workspaces/bravo",
                "last_successful": "some_key",
                "running_files": {
                    "beta.bst": ["some_file"]
                }
            }
        }
    }, {
        "format-version": 2,
        "workspaces": {
            "alpha.bst": {
                "path": "/workspaces/bravo",
                "last_successful": "some_key",
                "running_files": {
                    "beta.bst": ["some_file"]
                }
            }
        }
    })
])
def test_list_supported_workspace(cli, tmpdir, datafiles, workspace_cfg, expected):
    def parse_dict_as_yaml(node):
        tempfile = os.path.join(str(tmpdir), 'yaml_dump')
        _yaml.dump(node, tempfile)
        return _yaml.node_sanitize(_yaml.load(tempfile))

    project = os.path.join(datafiles.dirname, datafiles.basename)
    os.makedirs(os.path.join(project, '.bst'))
    workspace_config_path = os.path.join(project, '.bst', 'workspaces.yml')

    _yaml.dump(workspace_cfg, workspace_config_path)

    # Check that we can still read workspace config that is in old format
    result = cli.run(project=project, args=['workspace', 'list'])
    result.assert_success()

    loaded_config = _yaml.node_sanitize(_yaml.load(workspace_config_path))

    # Check that workspace config remains the same if no modifications
    # to workspaces were made
    assert loaded_config == parse_dict_as_yaml(workspace_cfg)

    # Create a test bst file
    bin_files_path = os.path.join(project, 'files', 'bin-files')
    element_path = os.path.join(project, 'elements')
    element_name = 'workspace-test.bst'
    workspace = os.path.join(str(tmpdir), 'workspace')

    # Create our repo object of the given source type with
    # the bin files, and then collect the initial ref.
    #
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(bin_files_path)

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

    # Make a change to the workspaces file
    result = cli.run(project=project, args=['workspace', 'open', element_name, workspace])
    result.assert_success()
    result = cli.run(project=project, args=['workspace', 'close', '--remove-dir', element_name])
    result.assert_success()

    # Check that workspace config is converted correctly if necessary
    loaded_config = _yaml.node_sanitize(_yaml.load(workspace_config_path))
    assert loaded_config == parse_dict_as_yaml(expected)
