import os
import pytest

from tests.testutils import cli_integration as cli
from tests.testutils.integration import assert_contains
from tests.testutils.site import IS_LINUX

pytestmark = pytest.mark.integration

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), '..', '..', 'doc', 'examples', 'autotools'
)


# Tests a build of the autotools amhello project on a alpine-linux base runtime
@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_autotools_build(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')

    # Check that the project can be built correctly.
    result = cli.run(project=project, args=['build', 'hello.bst'])
    result.assert_success()

    result = cli.run(project=project, args=['checkout', 'hello.bst', checkout])
    result.assert_success()

    assert_contains(checkout, ['/usr', '/usr/lib', '/usr/bin',
                               '/usr/share', '/usr/lib/debug',
                               '/usr/lib/debug/usr', '/usr/lib/debug/usr/bin',
                               '/usr/lib/debug/usr/bin/hello',
                               '/usr/bin/hello',
                               '/usr/share/doc', '/usr/share/doc/amhello',
                               '/usr/share/doc/amhello/README'])


# Test running an executable built with autotools.
@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_autotools_run(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    result = cli.run(project=project, args=['build', 'hello.bst'])
    result.assert_success()

    result = cli.run(project=project, args=['shell', 'hello.bst', 'hello'])
    result.assert_success()
    assert result.output == 'Hello World!\nThis is amhello 1.0.\n'
