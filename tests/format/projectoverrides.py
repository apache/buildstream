
import os
import pytest
from buildstream import _yaml
from tests.testutils.runcli import cli

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project-overrides"
)


@pytest.mark.datafiles(DATA_DIR)
def test_prepend_configure_commands(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, 'prepend-configure-commands')
    result = cli.run(project=project, silent=True, args=[
        'show',
        '--deps', 'none',
        '--format', '%{config}',
        'element.bst'])

    result.assert_success()
    loaded = _yaml.load_data(result.output)
    config_commands = loaded['configure-commands']
    assert len(config_commands) == 3
    assert config_commands[0] == 'echo "Hello World!"'
