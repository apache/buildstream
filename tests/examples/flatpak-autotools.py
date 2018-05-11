import os
import pytest

from tests.testutils import cli_integration as cli
from tests.testutils.integration import assert_contains


pytestmark = pytest.mark.example


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), '..', '..', 'doc', 'examples', 'flatpak-autotools'
)


# Test that a build upon flatpak runtime 'works' - we use the autotools sample
# amhello project for this.
@pytest.mark.example
@pytest.mark.datafiles(DATA_DIR)
def test_autotools_build(cli, tmpdir, datafiles):
    print(datafiles)
    project = os.path.join(datafiles.dirname, datafiles.basename)
    print(project)
    checkout = os.path.join(cli.directory, 'checkout')
    element_name = 'flatpak-autotools.bst'

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['checkout', element_name, checkout])
    assert result.exit_code == 0

    assert_contains(checkout, ['/usr', '/usr/lib', '/usr/bin',
                               '/usr/share', '/usr/lib/debug',
                               '/usr/lib/debug/hello', '/usr/bin/hello',
                               '/usr/share/doc', '/usr/share/doc/amhello',
                               '/usr/share/doc/amhello/README'])


# Test running an executable built with autotools
@pytest.mark.datafiles(DATA_DIR)
def test_autotools_run(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_name = 'flatpak-autotools.bst'

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['shell', element_name, '/usr/bin/hello'])
    assert result.exit_code == 0
    assert result.output == 'Hello World!\nThis is amhello 1.0.\n'
