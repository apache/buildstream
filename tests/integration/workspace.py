import os
import pytest

from tests.testutils import cli_integration as cli


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
def test_workspace_mount(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    workspace = os.path.join(cli.directory, 'workspace')
    element_name = 'workspace/workspace-mount.bst'

    res = cli.run(project=project, args=['workspace', 'open', element_name, workspace])
    assert res.exit_code == 0

    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    assert os.path.exists(os.path.join(cli.directory, 'workspace'))
