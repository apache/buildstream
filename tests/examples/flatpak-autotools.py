# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream2.testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream2.testing.integration import assert_contains
from tests.testutils.site import HAVE_OSTREE, IS_LINUX, MACHINE_ARCH


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
@pytest.mark.skipif(MACHINE_ARCH != 'x86-64',
                    reason='Examples are written for x86-64')
@pytest.mark.skipif(not IS_LINUX or not HAVE_OSTREE, reason='Only available on linux with ostree')
@pytest.mark.datafiles(DATA_DIR)
def test_autotools_build(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, 'checkout')
    workaround_setuptools_bug(project)

    result = cli.run(project=project, args=['build', 'hello.bst'])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['artifact', 'checkout', 'hello.bst', '--directory', checkout])
    assert result.exit_code == 0

    assert_contains(checkout, ['/usr', '/usr/lib', '/usr/bin',
                               '/usr/share',
                               '/usr/bin/hello', '/usr/share/doc',
                               '/usr/share/doc/amhello',
                               '/usr/share/doc/amhello/README'])


# Test running an executable built with autotools
@pytest.mark.skipif(MACHINE_ARCH != 'x86-64',
                    reason='Examples are written for x86-64')
@pytest.mark.skipif(not IS_LINUX or not HAVE_OSTREE, reason='Only available on linux with ostree')
@pytest.mark.datafiles(DATA_DIR)
def test_autotools_run(cli, datafiles):
    project = str(datafiles)
    workaround_setuptools_bug(project)

    result = cli.run(project=project, args=['build', 'hello.bst'])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['shell', 'hello.bst', '/usr/bin/hello'])
    assert result.exit_code == 0
    assert result.output == 'Hello World!\nThis is amhello 1.0.\n'
