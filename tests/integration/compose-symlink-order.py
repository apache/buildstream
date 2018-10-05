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
def test_compose_symlinks_bad_order(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, 'checkout')
    element_path = os.path.join(project, 'elements')

    a_files = os.path.join(project, 'files', 'compose-symlink-order', 'a')
    os.symlink('b', os.path.join(a_files, 'a'),
               target_is_directory=True)

    result = cli.run(project=project,
                     args=['build', 'compose-symlink-order/compose.bst'])
    result.assert_success()

    result = cli.run(project=project,
                     args=['checkout', 'compose-symlink-order/compose.bst',
                           checkout])
    result.assert_success()

    assert os.path.exists(os.path.join(checkout, 'a/c/d'))
    assert os.path.exists(os.path.join(checkout, 'b/c/d'))
    assert os.path.islink(os.path.join(checkout, 'a'))
