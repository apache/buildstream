import os
import pytest

from tests.testutils import cli_integration as cli
from tests.testutils.integration import assert_contains
from tests.testutils.site import IS_LINUX

pytestmark = pytest.mark.integration

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), '..', '..', 'doc', 'examples', 'cmake'
)


# Tests a build using cmake with the C complier from alpine-linux base runtime
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
                               '/usr/share',
                               '/bin/hello_buildstream'])


# Test running an executable built with cmake.
@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_autotools_run(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    result = cli.run(project=project, args=['build', 'hello.bst'])
    result.assert_success()

    result = cli.run(project=project, args=['shell', 'hello.bst', 'hello_buildstream'])
    result.assert_success()
    assert result.output == 'Hello, World!\n'
