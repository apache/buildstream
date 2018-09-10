import os
import pytest

from tests.testutils import cli_integration as cli
from tests.testutils.integration import assert_contains
from tests.testutils.site import IS_LINUX

pytestmark = pytest.mark.integration

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), '..', '..', 'doc', 'examples', 'out-of-source-build'
)


# Tests a build of the autotools amhello project on a alpine-linux base runtime
@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_project_build_projcet(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')

    # Check that the project can be built correctly.
    result = cli.run(project=project, args=['build', 'sourceroot.bst'])
    result.assert_success()

    result = cli.run(project=project, args=['checkout', 'sourceroot.bst', checkout])
    result.assert_success()

    assert_contains(checkout, ['/usr', '/usr/lib', '/usr/bin',
                               '/usr/share', '/usr/lib/debug',
                               '/bin/hello_buildstream'])


# Tests a build of the autotools amhello project on a alpine-linux base runtime
@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_project_build_main(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')

    # Check that the project can be built correctly.
    result = cli.run(project=project, args=['build', 'subfolder.bst'])
    result.assert_success()

    result = cli.run(project=project, args=['checkout', 'subfolder.bst', checkout])
    result.assert_success()

    assert_contains(checkout, ['/usr', '/usr/lib', '/usr/bin',
                               '/usr/share', '/usr/lib/debug',
                               '/bin/hello_buildstream'])


# Test running an executable built with autotools.
@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_run_project(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    result = cli.run(project=project, args=['build', 'sourceroot.bst'])
    result.assert_success()

    result = cli.run(project=project, args=['shell', 'sourceroot.bst', 'hello_buildstream'])
    result.assert_success()
    assert result.output == 'Hello, World! Built from the source root.\n'


# Test running an executable built with autotools.
@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_run_main(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    result = cli.run(project=project, args=['build', 'subfolder.bst'])
    result.assert_success()

    result = cli.run(project=project, args=['shell', 'subfolder.bst', 'hello_buildstream'])
    result.assert_success()
    assert result.output == 'Hello, World! Built from a subdirectory of the source.\n'
