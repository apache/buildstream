import os
import pytest

from tests.testutils import cli_integration as cli
from tests.testutils.integration import assert_contains
from tests.testutils.site import IS_LINUX


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), '..', '..', 'doc', 'examples', 'flatpak-autotools'
)


# FIXME: Workaround a setuptools bug which fails to include symbolic
#        links in the source distribution.
#
#        Remove this hack once setuptools is fixed
def workaround_setuptools_bug(project):
    os.makedirs(os.path.join(project, "files", "links"), exist_ok=True)
    try:
        os.symlink(os.path.join("usr", "lib"), os.path.join(project, "files", "links", "lib"))
        os.symlink(os.path.join("usr", "bin"), os.path.join(project, "files", "links", "bin"))
        os.symlink(os.path.join("usr", "etc"), os.path.join(project, "files", "links", "etc"))
    except FileExistsError:
        # If the files exist, we're running from a git checkout and
        # not a source distribution, no need to complain
        pass


# Test that a build upon flatpak runtime 'works' - we use the autotools sample
# amhello project for this.
@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_autotools_build(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    workaround_setuptools_bug(project)

    result = cli.run(project=project, args=['build', 'hello.bst'])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['checkout', 'hello.bst', checkout])
    assert result.exit_code == 0

    assert_contains(checkout, ['/usr', '/usr/lib', '/usr/bin',
                               '/usr/share', '/usr/lib/debug',
                               '/usr/lib/debug/usr', '/usr/lib/debug/usr/bin',
                               '/usr/lib/debug/usr/bin/hello',
                               '/usr/bin/hello', '/usr/share/doc',
                               '/usr/share/doc/amhello',
                               '/usr/share/doc/amhello/README'])


# Test running an executable built with autotools
@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_autotools_run(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    workaround_setuptools_bug(project)

    result = cli.run(project=project, args=['build', 'hello.bst'])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['shell', 'hello.bst', '/usr/bin/hello'])
    assert result.exit_code == 0
    assert result.output == 'Hello World!\nThis is amhello 1.0.\n'
