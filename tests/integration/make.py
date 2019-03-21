import os
import pytest

from buildstream.plugintestutils import cli_integration as cli
from buildstream.plugintestutils.integration import assert_contains
from tests.testutils.site import HAVE_SANDBOX


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


# Test that a make build 'works' - we use the make sample
# makehello project for this.
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_make_build(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, 'checkout')
    element_name = 'make/makehello.bst'

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['artifact', 'checkout', element_name, '--directory', checkout])
    assert result.exit_code == 0

    assert_contains(checkout, ['/usr', '/usr/bin',
                               '/usr/bin/hello'])


# Test running an executable built with make
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_make_run(cli, datafiles):
    project = str(datafiles)
    element_name = 'make/makehello.bst'

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['shell', element_name, '/usr/bin/hello'])
    assert result.exit_code == 0
    assert result.output == 'Hello, world\n'
