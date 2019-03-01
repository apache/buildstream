import os
import pytest

from buildstream.plugintestutils import cli_integration as cli
from buildstream.plugintestutils.integration import assert_contains
from tests.testutils.site import HAVE_SANDBOX


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


# Test that an autotools build 'works' - we use the autotools sample
# amhello project for this.
@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_autotools_build(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_name = 'autotools/amhello.bst'

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['artifact', 'checkout', element_name, '--directory', checkout])
    assert result.exit_code == 0

    assert_contains(checkout, ['/usr', '/usr/lib', '/usr/bin',
                               '/usr/share',
                               '/usr/bin/hello', '/usr/share/doc',
                               '/usr/share/doc/amhello',
                               '/usr/share/doc/amhello/README'])


# Test that an autotools build 'works' - we use the autotools sample
# amhello project for this.
@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_autotools_confroot_build(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_name = 'autotools/amhelloconfroot.bst'

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['artifact', 'checkout', element_name, '--directory', checkout])
    assert result.exit_code == 0

    assert_contains(checkout, ['/usr', '/usr/lib', '/usr/bin',
                               '/usr/share',
                               '/usr/bin/hello', '/usr/share/doc',
                               '/usr/share/doc/amhello',
                               '/usr/share/doc/amhello/README'])


# Test running an executable built with autotools
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_autotools_run(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_name = 'autotools/amhello.bst'

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['shell', element_name, '/usr/bin/hello'])
    assert result.exit_code == 0
    assert result.output == 'Hello World!\nThis is amhello 1.0.\n'
