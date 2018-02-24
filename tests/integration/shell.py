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
#    element (str): The element to build and run a shell with
#
def execute_shell(cli, project, command, element='base.bst'):
    # Ensure the element is built
    result = cli.run(project=project, args=['build', element])
    assert result.exit_code == 0

    return cli.run(project=project,
                   args=['shell', element, '--'] + command)


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
