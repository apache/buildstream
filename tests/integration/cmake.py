import os
import pytest

from tests.testutils import cli_integration as cli
from tests.testutils.integration import assert_contains
from tests.testutils.site import HAVE_BWRAP, IS_LINUX


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
def test_cmake_build(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_name = 'cmake/cmakehello.bst'

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['checkout', element_name, checkout])
    assert result.exit_code == 0

    assert_contains(checkout, ['/usr', '/usr/bin', '/usr/bin/hello'])


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
def test_cmake_confroot_build(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_name = 'cmake/cmakeconfroothello.bst'

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['checkout', element_name, checkout])
    assert result.exit_code == 0

    assert_contains(checkout, ['/usr', '/usr/bin', '/usr/bin/hello'])


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
def test_cmake_run(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_name = 'cmake/cmakehello.bst'

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['shell', element_name, '/usr/bin/hello'])
    assert result.exit_code == 0

    assert result.output == """Hello World!
This is hello.
"""
