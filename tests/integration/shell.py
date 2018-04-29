import os
import pytest

from buildstream import _yaml
from buildstream._exceptions import ErrorDomain

from tests.testutils import cli_integration as cli


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


# execute_shell()
#
# Helper to run `bst shell` and first ensure that the element is built
#
# Args:
#    cli (Cli): The cli runner fixture
#    project (str): The project directory
#    command (list): The command argv list
#    config (dict): A project.conf dictionary to composite over the default
#    mount (tuple): A (host, target) tuple for the `--mount` option
#    element (str): The element to build and run a shell with
#    isolate (bool): Whether to pass --isolate to `bst shell`
#
def execute_shell(cli, project, command, *, config=None, mount=None, element='base.bst', isolate=False):
    # Ensure the element is built
    result = cli.run(project=project, project_config=config, args=['build', element])
    assert result.exit_code == 0

    args = ['shell']
    if isolate:
        args += ['--isolate']
    if mount is not None:
        host_path, target_path = mount
        args += ['--mount', host_path, target_path]
    args += [element, '--'] + command

    return cli.run(project=project, project_config=config, args=args)


# Test running something through a shell, allowing it to find the
# executable
@pytest.mark.datafiles(DATA_DIR)
def test_shell(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    result = execute_shell(cli, project, ["echo", "Ponies!"])
    assert result.exit_code == 0
    assert result.output == "Ponies!\n"


# Test running an executable directly
@pytest.mark.datafiles(DATA_DIR)
def test_executable(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    result = execute_shell(cli, project, ["/bin/echo", "Horseys!"])
    assert result.exit_code == 0
    assert result.output == "Horseys!\n"


# Test shell environment variable explicit assignments
@pytest.mark.parametrize("animal", [("Horse"), ("Pony")])
@pytest.mark.datafiles(DATA_DIR)
def test_env_assign(cli, tmpdir, datafiles, animal):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    expected = animal + '\n'

    result = execute_shell(cli, project, ['/bin/sh', '-c', 'echo ${ANIMAL}'], config={
        'shell': {
            'environment': {
                'ANIMAL': animal
            }
        }
    })

    assert result.exit_code == 0
    assert result.output == expected


# Test shell environment variable explicit assignments with host env var expansion
@pytest.mark.parametrize("animal", [("Horse"), ("Pony")])
@pytest.mark.datafiles(DATA_DIR)
def test_env_assign_expand_host_environ(cli, tmpdir, datafiles, animal):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    expected = 'The animal is: {}\n'.format(animal)

    os.environ['BEAST'] = animal

    result = execute_shell(cli, project, ['/bin/sh', '-c', 'echo ${ANIMAL}'], config={
        'shell': {
            'environment': {
                'ANIMAL': 'The animal is: ${BEAST}'
            }
        }
    })

    assert result.exit_code == 0
    assert result.output == expected


# Test that shell environment variable explicit assignments are discarded
# when running an isolated shell
@pytest.mark.parametrize("animal", [("Horse"), ("Pony")])
@pytest.mark.datafiles(DATA_DIR)
def test_env_assign_isolated(cli, tmpdir, datafiles, animal):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    result = execute_shell(cli, project, ['/bin/sh', '-c', 'echo ${ANIMAL}'], isolate=True, config={
        'shell': {
            'environment': {
                'ANIMAL': animal
            }
        }
    })

    assert result.exit_code == 0
    assert result.output == '\n'


# Test running an executable in a runtime with no shell (i.e., no
# /bin/sh)
@pytest.mark.datafiles(DATA_DIR)
def test_no_shell(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_path = os.path.join(project, 'elements')
    element_name = 'shell/no-shell.bst'

    # Create an element that removes /bin/sh from the base runtime
    element = {
        'kind': 'script',
        'depends': [{
            'filename': 'base.bst',
            'type': 'build'
        }],
        'variables': {
            'install-root': '/'
        },
        'config': {
            'commands': [
                'rm /bin/sh'
            ]
        }
    }
    os.makedirs(os.path.dirname(os.path.join(element_path, element_name)), exist_ok=True)
    _yaml.dump(element, os.path.join(element_path, element_name))

    result = execute_shell(cli, project, ['/bin/echo', 'Pegasissies!'], element=element_name)
    assert result.exit_code == 0
    assert result.output == "Pegasissies!\n"


# Test that bind mounts defined in project.conf work
@pytest.mark.parametrize("path", [("/etc/pony.conf"), ("/usr/share/pony/pony.txt")])
@pytest.mark.datafiles(DATA_DIR)
def test_host_files(cli, tmpdir, datafiles, path):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    ponyfile = os.path.join(project, 'files', 'shell-mount', 'pony.txt')
    result = execute_shell(cli, project, ['cat', path], config={
        'shell': {
            'host-files': [
                {
                    'host_path': ponyfile,
                    'path': path
                }
            ]
        }
    })
    assert result.exit_code == 0
    assert result.output == 'pony\n'


# Test that bind mounts defined in project.conf work
@pytest.mark.parametrize("path", [("/etc"), ("/usr/share/pony")])
@pytest.mark.datafiles(DATA_DIR)
def test_host_files_expand_environ(cli, tmpdir, datafiles, path):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    hostpath = os.path.join(project, 'files', 'shell-mount')
    fullpath = os.path.join(path, 'pony.txt')

    os.environ['BASE_PONY'] = path
    os.environ['HOST_PONY_PATH'] = hostpath

    result = execute_shell(cli, project, ['cat', fullpath], config={
        'shell': {
            'host-files': [
                {
                    'host_path': '${HOST_PONY_PATH}/pony.txt',
                    'path': '${BASE_PONY}/pony.txt'
                }
            ]
        }
    })
    assert result.exit_code == 0
    assert result.output == 'pony\n'


# Test that bind mounts defined in project.conf dont mount in isolation
@pytest.mark.parametrize("path", [("/etc/pony.conf"), ("/usr/share/pony/pony.txt")])
@pytest.mark.datafiles(DATA_DIR)
def test_isolated_no_mount(cli, tmpdir, datafiles, path):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    ponyfile = os.path.join(project, 'files', 'shell-mount', 'pony.txt')
    result = execute_shell(cli, project, ['cat', path], isolate=True, config={
        'shell': {
            'host-files': [
                {
                    'host_path': ponyfile,
                    'path': path
                }
            ]
        }
    })
    assert result.exit_code != 0


# Test that we warn about non-existing files on the host if the mount is not
# declared as optional, and that there is no warning if it is optional
@pytest.mark.parametrize("optional", [("mandatory"), ("optional")])
@pytest.mark.datafiles(DATA_DIR)
def test_host_files_missing(cli, tmpdir, datafiles, optional):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    ponyfile = os.path.join(project, 'files', 'shell-mount', 'horsy.txt')

    if optional == "optional":
        option = True
    else:
        option = False

    # Assert that we did successfully run something in the shell anyway
    result = execute_shell(cli, project, ['echo', 'Hello'], config={
        'shell': {
            'host-files': [
                {
                    'host_path': ponyfile,
                    'path': '/etc/pony.conf',
                    'optional': option
                }
            ]
        }
    })
    assert result.exit_code == 0
    assert result.output == 'Hello\n'

    if option:
        # Assert that there was no warning about the mount
        assert ponyfile not in result.stderr
    else:
        # Assert that there was a warning about the mount
        assert ponyfile in result.stderr


# Test that bind mounts defined in project.conf work
@pytest.mark.parametrize("path", [("/etc/pony.conf"), ("/usr/share/pony/pony.txt")])
@pytest.mark.datafiles(DATA_DIR)
def test_cli_mount(cli, tmpdir, datafiles, path):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    ponyfile = os.path.join(project, 'files', 'shell-mount', 'pony.txt')

    result = execute_shell(cli, project, ['cat', path], mount=(ponyfile, path))
    assert result.exit_code == 0
    assert result.output == 'pony\n'


# Test that we can see the workspace files in a shell
@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
def test_workspace_visible(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    workspace = os.path.join(cli.directory, 'workspace')
    element_name = 'workspace/workspace-mount-fail.bst'

    # Open a workspace on our build failing element
    #
    res = cli.run(project=project, args=['workspace', 'open', element_name, workspace])
    assert res.exit_code == 0

    # Ensure the dependencies of our build failing element are built
    result = cli.run(project=project, args=['build', 'base.bst'])
    assert result.exit_code == 0

    # Obtain a copy of the hello.c content from the workspace
    #
    workspace_hello_path = os.path.join(cli.directory, 'workspace', 'hello.c')
    assert os.path.exists(workspace_hello_path)
    with open(workspace_hello_path, 'r') as f:
        workspace_hello = f.read()

    # Cat the hello.c file from a bst shell command, and assert
    # that we got the same content here
    #
    result = cli.run(project=project, args=[
        'shell', '--build', element_name, '--', 'cat', 'hello.c'
    ])
    assert result.exit_code == 0
    assert result.output == workspace_hello


# Test that we can see the workspace files in a shell
@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
def test_sysroot_workspace_visible(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    workspace = os.path.join(cli.directory, 'workspace')
    element_name = 'workspace/workspace-mount-fail.bst'

    # Open a workspace on our build failing element
    #
    res = cli.run(project=project, args=['workspace', 'open', element_name, workspace])
    assert res.exit_code == 0

    # Ensure the dependencies of our build failing element are built
    result = cli.run(project=project, args=['build', element_name])
    result.assert_main_error(ErrorDomain.STREAM, None)

    # Discover the sysroot of the failed build directory, after one
    # failed build, there should be only one directory there.
    #
    build_base = os.path.join(cli.directory, 'build')
    build_dirs = os.listdir(path=build_base)
    assert len(build_dirs) == 1
    build_dir = os.path.join(build_base, build_dirs[0])

    # Obtain a copy of the hello.c content from the workspace
    #
    workspace_hello_path = os.path.join(cli.directory, 'workspace', 'hello.c')
    assert os.path.exists(workspace_hello_path)
    with open(workspace_hello_path, 'r') as f:
        workspace_hello = f.read()

    # Cat the hello.c file from a bst shell command, and assert
    # that we got the same content here
    #
    result = cli.run(project=project, args=[
        'shell', '--build', '--sysroot', build_dir, element_name, '--', 'cat', 'hello.c'
    ])
    assert result.exit_code == 0
    assert result.output == workspace_hello
