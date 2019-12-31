# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream.testing.integration import assert_contains
from buildstream.testing._utils.site import IS_LINUX, MACHINE_ARCH, HAVE_SANDBOX

pytestmark = pytest.mark.integration

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "doc", "examples", "autotools")


# Tests a build of the autotools amhello project on a alpine-linux base runtime
@pytest.mark.skipif(MACHINE_ARCH != "x86-64", reason="Examples are written for x86-64")
@pytest.mark.skipif(not IS_LINUX or not HAVE_SANDBOX, reason="Only available on linux with sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_autotools_build(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")

    # Check that the project can be built correctly.
    result = cli.run(project=project, args=["build", "hello.bst"])
    result.assert_success()

    result = cli.run(project=project, args=["artifact", "checkout", "hello.bst", "--directory", checkout])
    result.assert_success()

    assert_contains(
        checkout,
        [
            "/usr",
            "/usr/lib",
            "/usr/bin",
            "/usr/share",
            "/usr/bin/hello",
            "/usr/share/doc",
            "/usr/share/doc/amhello",
            "/usr/share/doc/amhello/README",
        ],
    )


# Test running an executable built with autotools.
@pytest.mark.skipif(MACHINE_ARCH != "x86-64", reason="Examples are written for x86-64")
@pytest.mark.skipif(not IS_LINUX or not HAVE_SANDBOX, reason="Only available on linux with sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_autotools_run(cli, datafiles):
    project = str(datafiles)

    result = cli.run(project=project, args=["build", "hello.bst"])
    result.assert_success()

    result = cli.run(project=project, args=["shell", "hello.bst", "hello"])
    result.assert_success()
    assert result.output == "Hello World!\nThis is amhello 1.0.\n"
