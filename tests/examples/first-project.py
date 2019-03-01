import os
import pytest

from buildstream.plugintestutils import cli_integration as cli
from buildstream.plugintestutils.integration import assert_contains
from tests.testutils.site import IS_LINUX


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), '..', '..', 'doc', 'examples', 'first-project'
)


@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_first_project_build_checkout(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')

    result = cli.run(project=project, args=['build', 'hello.bst'])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['artifact', 'checkout', 'hello.bst', '--directory', checkout])
    assert result.exit_code == 0

    assert_contains(checkout, ['/hello.world'])
