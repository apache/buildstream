import os
import pytest

from buildstream.plugintestutils import cli_integration as cli
from buildstream.plugintestutils.integration import assert_contains
from tests.testutils.site import HAVE_BWRAP, IS_LINUX, MACHINE_ARCH

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), '..', '..', 'doc', 'examples', 'autotools'
)


# Tests a build of the autotools amhello project on a alpine-linux base runtime
@pytest.mark.skipif(MACHINE_ARCH != 'x86-64',
                    reason='Examples are writtent for x86-64')
@pytest.mark.skipif(not IS_LINUX or not HAVE_BWRAP, reason='Only available on linux with bubblewrap')
@pytest.mark.datafiles(DATA_DIR)
def test_autotools_build(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')

    # Check that the project can be built correctly.
    result = cli.run(project=project, args=['build', 'hello.bst'])
    result.assert_success()

    result = cli.run(project=project, args=['artifact', 'checkout', 'hello.bst', '--directory', checkout])
    result.assert_success()

    assert_contains(checkout, ['/usr', '/usr/lib', '/usr/bin',
                               '/usr/share',
                               '/usr/bin/hello',
                               '/usr/share/doc', '/usr/share/doc/amhello',
                               '/usr/share/doc/amhello/README'])


# Test running an executable built with autotools.
@pytest.mark.skipif(MACHINE_ARCH != 'x86-64',
                    reason='Examples are writtent for x86-64')
@pytest.mark.skipif(not IS_LINUX or not HAVE_BWRAP, reason='Only available on linux with bubblewrap')
@pytest.mark.datafiles(DATA_DIR)
def test_autotools_run(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    result = cli.run(project=project, args=['build', 'hello.bst'])
    result.assert_success()

    result = cli.run(project=project, args=['shell', 'hello.bst', 'hello'])
    result.assert_success()
    assert result.output == 'Hello World!\nThis is amhello 1.0.\n'
