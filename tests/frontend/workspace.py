import os
import pytest
import shutil
import subprocess
from ruamel.yaml.comments import CommentedSet
from tests.testutils import cli, create_repo, ALL_REPO_KINDS

from buildstream import _yaml
from buildstream._exceptions import ErrorDomain, LoadError, LoadErrorReason
from buildstream._workspaces import BST_WORKSPACE_FORMAT_VERSION

repo_kinds = [(kind) for kind in ALL_REPO_KINDS]

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


def open_workspace(cli, tmpdir, datafiles, kind, track, suffix=''):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    bin_files_path = os.path.join(project, 'files', 'bin-files')
    element_path = os.path.join(project, 'elements')
    element_name = 'workspace-test-{}{}.bst'.format(kind, suffix)
    workspace = os.path.join(str(tmpdir), 'workspace{}'.format(suffix))

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
def test_open_bzr_customize(cli, tmpdir, datafiles):
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
def test_open_force(cli, tmpdir, datafiles, kind):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, kind, False)

    # Close the workspace
    result = cli.run(project=project, args=[
        'workspace', 'close', element_name
    ])
    result.assert_success()

    # Assert the workspace dir still exists
    assert os.path.exists(workspace)

    # Now open the workspace again with --force, this should happily succeed
    result = cli.run(project=project, args=[
        'workspace', 'open', '--force', element_name, workspace
    ])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", repo_kinds)
def test_open_force_open(cli, tmpdir, datafiles, kind):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, kind, False)

    # Assert the workspace dir exists
    assert os.path.exists(workspace)

    # Now open the workspace again with --force, this should happily succeed
    result = cli.run(project=project, args=[
        'workspace', 'open', '--force', element_name, workspace
    ])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", repo_kinds)
def test_open_force_different_workspace(cli, tmpdir, datafiles, kind):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, kind, False, "-alpha")

    # Assert the workspace dir exists
    assert os.path.exists(workspace)

    hello_path = os.path.join(workspace, 'usr', 'bin', 'hello')
    hello1_path = os.path.join(workspace, 'usr', 'bin', 'hello1')

    tmpdir = os.path.join(str(tmpdir), "-beta")
    shutil.move(hello_path, hello1_path)
    element_name2, project2, workspace2 = open_workspace(cli, tmpdir, datafiles, kind, False, "-beta")

    # Assert the workspace dir exists
    assert os.path.exists(workspace2)

    # Assert that workspace 1 contains the modified file
    assert os.path.exists(hello1_path)

    # Assert that workspace 2 contains the unmodified file
    assert os.path.exists(os.path.join(workspace2, 'usr', 'bin', 'hello'))

    # Now open the workspace again with --force, this should happily succeed
    result = cli.run(project=project, args=[
        'workspace', 'open', '--force', element_name2, workspace
    ])

    # Assert that the file in workspace 1 has been replaced
    # With the file from workspace 2
    assert os.path.exists(hello_path)
    assert not os.path.exists(hello1_path)

    result.assert_success()


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
def test_close_removed(cli, tmpdir, datafiles):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, 'git', False)

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
def test_close_nonexistant_element(cli, tmpdir, datafiles):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, 'git', False)
    element_path = os.path.join(datafiles.dirname, datafiles.basename, 'elements', element_name)

    # First brutally remove the element.bst file, ensuring that
    # the element does not exist anymore in the project where
    # we want to close the workspace.
    os.remove(element_path)

    # Close the workspace
    result = cli.run(project=project, args=[
        'workspace', 'close', '--remove-dir', element_name
    ])
    result.assert_success()

    # Assert the workspace dir has been deleted
    assert not os.path.exists(workspace)


@pytest.mark.datafiles(DATA_DIR)
def test_close_multiple(cli, tmpdir, datafiles):
    tmpdir_alpha = os.path.join(str(tmpdir), 'alpha')
    tmpdir_beta = os.path.join(str(tmpdir), 'beta')
    alpha, project, workspace_alpha = open_workspace(
        cli, tmpdir_alpha, datafiles, 'git', False, suffix='-alpha')
    beta, project, workspace_beta = open_workspace(
        cli, tmpdir_beta, datafiles, 'git', False, suffix='-beta')

    # Close the workspaces
    result = cli.run(project=project, args=[
        'workspace', 'close', '--remove-dir', alpha, beta
    ])
    result.assert_success()

    # Assert the workspace dirs have been deleted
    assert not os.path.exists(workspace_alpha)
    assert not os.path.exists(workspace_beta)


@pytest.mark.datafiles(DATA_DIR)
def test_close_all(cli, tmpdir, datafiles):
    tmpdir_alpha = os.path.join(str(tmpdir), 'alpha')
    tmpdir_beta = os.path.join(str(tmpdir), 'beta')
    alpha, project, workspace_alpha = open_workspace(
        cli, tmpdir_alpha, datafiles, 'git', False, suffix='-alpha')
    beta, project, workspace_beta = open_workspace(
        cli, tmpdir_beta, datafiles, 'git', False, suffix='-beta')

    # Close the workspaces
    result = cli.run(project=project, args=[
        'workspace', 'close', '--remove-dir', '--all'
    ])
    result.assert_success()

    # Assert the workspace dirs have been deleted
    assert not os.path.exists(workspace_alpha)
    assert not os.path.exists(workspace_beta)


@pytest.mark.datafiles(DATA_DIR)
def test_reset(cli, tmpdir, datafiles):
    # Open the workspace
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, 'git', False)

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
def test_reset_multiple(cli, tmpdir, datafiles):
    # Open the workspaces
    tmpdir_alpha = os.path.join(str(tmpdir), 'alpha')
    tmpdir_beta = os.path.join(str(tmpdir), 'beta')
    alpha, project, workspace_alpha = open_workspace(
        cli, tmpdir_alpha, datafiles, 'git', False, suffix='-alpha')
    beta, project, workspace_beta = open_workspace(
        cli, tmpdir_beta, datafiles, 'git', False, suffix='-beta')

    # Modify workspaces
    shutil.rmtree(os.path.join(workspace_alpha, 'usr', 'bin'))
    os.makedirs(os.path.join(workspace_beta, 'etc'))
    with open(os.path.join(workspace_beta, 'etc', 'pony.conf'), 'w') as f:
        f.write("PONY='pink'")

    # Now reset the open workspaces, this should have the
    # effect of reverting our changes.
    result = cli.run(project=project, args=[
        'workspace', 'reset', alpha, beta,
    ])
    result.assert_success()
    assert os.path.exists(os.path.join(workspace_alpha, 'usr', 'bin', 'hello'))
    assert not os.path.exists(os.path.join(workspace_beta, 'etc', 'pony.conf'))


@pytest.mark.datafiles(DATA_DIR)
def test_reset_all(cli, tmpdir, datafiles):
    # Open the workspaces
    tmpdir_alpha = os.path.join(str(tmpdir), 'alpha')
    tmpdir_beta = os.path.join(str(tmpdir), 'beta')
    alpha, project, workspace_alpha = open_workspace(
        cli, tmpdir_alpha, datafiles, 'git', False, suffix='-alpha')
    beta, project, workspace_beta = open_workspace(
        cli, tmpdir_beta, datafiles, 'git', False, suffix='-beta')

    # Modify workspaces
    shutil.rmtree(os.path.join(workspace_alpha, 'usr', 'bin'))
    os.makedirs(os.path.join(workspace_beta, 'etc'))
    with open(os.path.join(workspace_beta, 'etc', 'pony.conf'), 'w') as f:
        f.write("PONY='pink'")

    # Now reset the open workspace, this should have the
    # effect of reverting our changes.
    result = cli.run(project=project, args=[
        'workspace', 'reset', '--all'
    ])
    result.assert_success()
    assert os.path.exists(os.path.join(workspace_alpha, 'usr', 'bin', 'hello'))
    assert not os.path.exists(os.path.join(workspace_beta, 'etc', 'pony.conf'))


@pytest.mark.datafiles(DATA_DIR)
def test_list(cli, tmpdir, datafiles):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, 'git', False)

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
@pytest.mark.parametrize("strict", [("strict"), ("non-strict")])
def test_build(cli, tmpdir, datafiles, kind, strict):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, kind, False)
    checkout = os.path.join(str(tmpdir), 'checkout')

    # Modify workspace
    shutil.rmtree(os.path.join(workspace, 'usr', 'bin'))
    os.makedirs(os.path.join(workspace, 'etc'))
    with open(os.path.join(workspace, 'etc', 'pony.conf'), 'w') as f:
        f.write("PONY='pink'")

    # Configure strict mode
    strict_mode = True
    if strict != 'strict':
        strict_mode = False
    cli.configure({
        'projects': {
            'test': {
                'strict': strict_mode
            }
        }
    })

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
    assert not os.path.exists(os.path.join(checkout, 'usr', 'bin', 'hello'))


@pytest.mark.datafiles(DATA_DIR)
def test_buildable_no_ref(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_name = 'workspace-test-no-ref.bst'
    element_path = os.path.join(project, 'elements')

    # Write out our test target without any source ref
    repo = create_repo('git', str(tmpdir))
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config()
        ]
    }
    _yaml.dump(element,
               os.path.join(element_path,
                            element_name))

    # Assert that this target is not buildable when no workspace is associated.
    assert cli.get_element_state(project, element_name) == 'no reference'

    # Now open the workspace. We don't need to checkout the source though.
    workspace = os.path.join(str(tmpdir), 'workspace-no-ref')
    os.makedirs(workspace)
    args = ['workspace', 'open', '--no-checkout', element_name, workspace]
    result = cli.run(project=project, args=args)
    result.assert_success()

    # Assert that the target is now buildable.
    assert cli.get_element_state(project, element_name) == 'buildable'


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("modification", [("addfile"), ("removefile"), ("modifyfile")])
@pytest.mark.parametrize("strict", [("strict"), ("non-strict")])
def test_detect_modifications(cli, tmpdir, datafiles, modification, strict):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, 'git', False)
    checkout = os.path.join(str(tmpdir), 'checkout')

    # Configure strict mode
    strict_mode = True
    if strict != 'strict':
        strict_mode = False
    cli.configure({
        'projects': {
            'test': {
                'strict': strict_mode
            }
        }
    })

    # Build clean workspace
    assert cli.get_element_state(project, element_name) == 'buildable'
    assert cli.get_element_key(project, element_name) == "{:?<64}".format('')
    result = cli.run(project=project, args=['build', element_name])
    result.assert_success()
    assert cli.get_element_state(project, element_name) == 'cached'
    assert cli.get_element_key(project, element_name) != "{:?<64}".format('')

    # Modify the workspace in various different ways, ensuring we
    # properly detect the changes.
    #
    if modification == 'addfile':
        os.makedirs(os.path.join(workspace, 'etc'))
        with open(os.path.join(workspace, 'etc', 'pony.conf'), 'w') as f:
            f.write("PONY='pink'")
    elif modification == 'removefile':
        os.remove(os.path.join(workspace, 'usr', 'bin', 'hello'))
    elif modification == 'modifyfile':
        with open(os.path.join(workspace, 'usr', 'bin', 'hello'), 'w') as f:
            f.write('cookie')
    else:
        # This cannot be reached
        assert 0

    # First assert that the state is properly detected
    assert cli.get_element_state(project, element_name) == 'buildable'
    assert cli.get_element_key(project, element_name) == "{:?<64}".format('')

    # Since there are different things going on at `bst build` time
    # than `bst show` time, we also want to build / checkout again,
    # and ensure that the result contains what we expect.
    result = cli.run(project=project, args=['build', element_name])
    result.assert_success()
    assert cli.get_element_state(project, element_name) == 'cached'
    assert cli.get_element_key(project, element_name) != "{:?<64}".format('')

    # Checkout the result
    result = cli.run(project=project, args=[
        'checkout', element_name, checkout
    ])
    result.assert_success()

    # Check the result for the changes we made
    #
    if modification == 'addfile':
        filename = os.path.join(checkout, 'etc', 'pony.conf')
        assert os.path.exists(filename)
    elif modification == 'removefile':
        assert not os.path.exists(os.path.join(checkout, 'usr', 'bin', 'hello'))
    elif modification == 'modifyfile':
        with open(os.path.join(workspace, 'usr', 'bin', 'hello'), 'r') as f:
            data = f.read()
            assert data == 'cookie'
    else:
        # This cannot be reached
        assert 0


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
    {"format-version": BST_WORKSPACE_FORMAT_VERSION + 1}
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
        "format-version": BST_WORKSPACE_FORMAT_VERSION,
        "workspaces": {
            "alpha.bst": {
                "prepared": False,
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
        "format-version": BST_WORKSPACE_FORMAT_VERSION,
        "workspaces": {
            "alpha.bst": {
                "prepared": False,
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
        "format-version": BST_WORKSPACE_FORMAT_VERSION,
        "workspaces": {
            "alpha.bst": {
                "prepared": False,
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
        "format-version": BST_WORKSPACE_FORMAT_VERSION,
        "workspaces": {
            "alpha.bst": {
                "prepared": False,
                "path": "/workspaces/bravo",
                "last_successful": "some_key",
                "running_files": {
                    "beta.bst": ["some_file"]
                }
            }
        }
    }),
    # Test loading version 3
    ({
        "format-version": 3,
        "workspaces": {
            "alpha.bst": {
                "prepared": True,
                "path": "/workspaces/bravo",
                "running_files": {}
            }
        }
    }, {
        "format-version": BST_WORKSPACE_FORMAT_VERSION,
        "workspaces": {
            "alpha.bst": {
                "prepared": True,
                "path": "/workspaces/bravo",
                "running_files": {}
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


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", repo_kinds)
def test_inconsitent_pipeline_message(cli, tmpdir, datafiles, kind):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, kind, False)

    shutil.rmtree(workspace)

    result = cli.run(project=project, args=[
        'build', element_name
    ])
    result.assert_main_error(ErrorDomain.PIPELINE, "inconsistent-pipeline-workspaced")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("strict", [("strict"), ("non-strict")])
def test_cache_key_workspace_in_dependencies(cli, tmpdir, datafiles, strict):
    checkout = os.path.join(str(tmpdir), 'checkout')
    element_name, project, workspace = open_workspace(cli, os.path.join(str(tmpdir), 'repo-a'),
                                                      datafiles, 'git', False)

    element_path = os.path.join(project, 'elements')
    back_dep_element_name = 'workspace-test-back-dep.bst'

    # Write out our test target
    element = {
        'kind': 'compose',
        'depends': [
            {
                'filename': element_name,
                'type': 'build'
            }
        ]
    }
    _yaml.dump(element,
               os.path.join(element_path,
                            back_dep_element_name))

    # Modify workspace
    shutil.rmtree(os.path.join(workspace, 'usr', 'bin'))
    os.makedirs(os.path.join(workspace, 'etc'))
    with open(os.path.join(workspace, 'etc', 'pony.conf'), 'w') as f:
        f.write("PONY='pink'")

    # Configure strict mode
    strict_mode = True
    if strict != 'strict':
        strict_mode = False
    cli.configure({
        'projects': {
            'test': {
                'strict': strict_mode
            }
        }
    })

    # Build artifact with dependency's modified workspace
    assert cli.get_element_state(project, element_name) == 'buildable'
    assert cli.get_element_key(project, element_name) == "{:?<64}".format('')
    assert cli.get_element_state(project, back_dep_element_name) == 'waiting'
    assert cli.get_element_key(project, back_dep_element_name) == "{:?<64}".format('')
    result = cli.run(project=project, args=['build', back_dep_element_name])
    result.assert_success()
    assert cli.get_element_state(project, element_name) == 'cached'
    assert cli.get_element_key(project, element_name) != "{:?<64}".format('')
    assert cli.get_element_state(project, back_dep_element_name) == 'cached'
    assert cli.get_element_key(project, back_dep_element_name) != "{:?<64}".format('')
    result = cli.run(project=project, args=['build', back_dep_element_name])
    result.assert_success()

    # Checkout the result
    result = cli.run(project=project, args=[
        'checkout', back_dep_element_name, checkout
    ])
    result.assert_success()

    # Check that the pony.conf from the modified workspace exists
    filename = os.path.join(checkout, 'etc', 'pony.conf')
    assert os.path.exists(filename)

    # Check that the original /usr/bin/hello is not in the checkout
    assert not os.path.exists(os.path.join(checkout, 'usr', 'bin', 'hello'))
