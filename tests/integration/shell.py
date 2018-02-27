import os
import pytest

from buildstream import _yaml

from tests.testutils import cli_integration as cli


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


def create_project_conf(project_dir, config):
    project_file = os.path.join(project_dir, 'project.conf')
    config['name'] = 'test'
    config['element-path'] = 'elements'
    config['aliases'] = {
        'gnome7': 'https://gnome7.codethink.co.uk/',
        'project_dir': 'file://{}'.format(project_dir),
    }
    config['options'] = {
        'linux': {
            'type': 'bool',
            'description': 'Whether to expect a linux platform',
            'default': 'True'
        }
    }
    _yaml.dump(config, project_file)


# execute_shell()
#
# Helper to run `bst shell` and first ensure that the element is built
#
# Args:
#    cli (Cli): The cli runner fixture
#    project (str): The project directory
#    command (list): The command argv list
#    element (str): The element to build and run a shell with
#    isolate (bool): Whether to pass --isolate to `bst shell`
#
def execute_shell(cli, project, command, element='base.bst', isolate=False):
    # Ensure the element is built
    result = cli.run(project=project, args=['build', element])
    assert result.exit_code == 0

    args = ['shell']
    if isolate:
        args += ['--isolate']
    args += [element, '--'] + command

    return cli.run(project=project, args=args)


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
def test_inherit(cli, tmpdir, datafiles, animal):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    create_project_conf(project, {
        'shell': {
            'environment-inherit': ['ANIMAL']
        }
    })

    # Set the env var, and expect the same with added newline
    os.environ['ANIMAL'] = animal
    expected = animal + '\n'

    result = execute_shell(cli, project, ['/bin/sh', '-c', 'echo ${ANIMAL}'])
    assert result.exit_code == 0
    assert result.output == expected


# Test that environment variable inheritance is disabled with --isolate
@pytest.mark.parametrize("animal", [("Horse"), ("Pony")])
@pytest.mark.datafiles(DATA_DIR)
def test_isolated_no_inherit(cli, tmpdir, datafiles, animal):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    create_project_conf(project, {
        'shell': {
            'environment-inherit': ['ANIMAL']
        }
    })

    # Set the env var, but expect that it is not applied
    os.environ['ANIMAL'] = animal

    result = execute_shell(cli, project, ['/bin/sh', '-c', 'echo ${ANIMAL}'], isolate=True)
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

    create_project_conf(project, {
        'shell': {
            'host-files': [
                {
                    'host': ponyfile,
                    'sandbox': path
                }
            ]
        }
    })

    result = execute_shell(cli, project, ['cat', path])
    assert result.exit_code == 0
    assert result.output == 'pony\n'


# Test that bind mounts defined in project.conf dont mount in isolation
@pytest.mark.parametrize("path", [("/etc/pony.conf"), ("/usr/share/pony/pony.txt")])
@pytest.mark.datafiles(DATA_DIR)
def test_isolated_no_mount(cli, tmpdir, datafiles, path):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    ponyfile = os.path.join(project, 'files', 'shell-mount', 'pony.txt')

    create_project_conf(project, {
        'shell': {
            'host-files': [
                {
                    'host': ponyfile,
                    'sandbox': path
                }
            ]
        }
    })

    result = execute_shell(cli, project, ['cat', path], isolate=True)
    assert result.exit_code != 0


# Test that bind mounts which specify directories dont get mounted
@pytest.mark.datafiles(DATA_DIR)
def test_host_files_refuse_dir(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    ponydir = os.path.join(project, 'files', 'shell-mount')

    create_project_conf(project, {
        'shell': {
            'host-files': [
                {
                    'host': ponydir,
                    'sandbox': '/usr/share/pony'
                }
            ]
        }
    })

    # Assert that we did successfully run something in the shell anyway
    result = execute_shell(cli, project, ['echo', 'Hello'])
    assert result.exit_code == 0
    assert result.output == 'Hello\n'

    # Assert that there was some warning about refusing to mount
    assert ponydir in result.stderr


# Test that we warn about non-existing files on the host, but execute the shell anyway
@pytest.mark.datafiles(DATA_DIR)
def test_host_files_non_existing(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    ponyfile = os.path.join(project, 'files', 'shell-mount', 'horsy.txt')

    create_project_conf(project, {
        'shell': {
            'host-files': [
                {
                    'host': ponyfile,
                    'sandbox': '/etc/pony.conf'
                }
            ]
        }
    })

    # Assert that we did successfully run something in the shell anyway
    result = execute_shell(cli, project, ['echo', 'Hello'])
    assert result.exit_code == 0
    assert result.output == 'Hello\n'

    # Assert that there was some warning about refusing to mount
    assert ponyfile in result.stderr
