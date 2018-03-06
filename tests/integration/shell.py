import os
import pytest

from buildstream import _yaml

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


# Test host environment variable inheritance
@pytest.mark.parametrize("animal", [("Horse"), ("Pony")])
@pytest.mark.datafiles(DATA_DIR)
def test_env_inherit(cli, tmpdir, datafiles, animal):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # Set the env var, and expect the same with added newline
    os.environ['ANIMAL'] = animal
    expected = animal + '\n'

    result = execute_shell(cli, project, ['/bin/sh', '-c', 'echo ${ANIMAL}'], config={
        'shell': {
            'environment-inherit': ['ANIMAL']
        }
    })

    assert result.exit_code == 0
    assert result.output == expected


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


# Test that environment variable inheritance is disabled with --isolate
@pytest.mark.parametrize("animal", [("Horse"), ("Pony")])
@pytest.mark.datafiles(DATA_DIR)
def test_env_isolated_no_inherit(cli, tmpdir, datafiles, animal):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # Set the env var, but expect that it is not applied
    os.environ['ANIMAL'] = animal

    result = execute_shell(cli, project, ['/bin/sh', '-c', 'echo ${ANIMAL}'], isolate=True, config={
        'shell': {
            'environment-inherit': ['ANIMAL']
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
