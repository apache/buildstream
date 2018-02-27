import os
import pytest

from buildstream import _yaml

from tests.testutils import cli_integration as cli


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


@pytest.mark.datafiles(DATA_DIR)
def test_stack(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_name = 'stack/stack.bst'

    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    cli.run(project=project, args=['checkout', element_name, checkout])
    assert res.exit_code == 0

    with open(os.path.join(checkout, 'hi')) as f:
        hi = f.read()

    with open(os.path.join(checkout, 'another-hi')) as f:
        another_hi = f.read()

    assert hi == "Hi\n"
    assert another_hi == "Another hi\n"
