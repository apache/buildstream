# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream.testing.integration import assert_contains
from buildstream.testing._utils.site import HAVE_SANDBOX


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


# Test that an autotools build 'works' - we use the autotools sample
# amhello project for this.
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_autotools_build(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    element_name = "autotools/amhello.bst"

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    assert result.exit_code == 0

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

    # Check the log
    result = cli.run(project=project, args=["artifact", "log", element_name])
    assert result.exit_code == 0
    log = result.output

    # Verify we get expected output exactly once
    assert log.count("Making all in src") == 1


# Test that an autotools build 'works' - we use the autotools sample
# amhello project for this.
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_autotools_confroot_build(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    element_name = "autotools/amhelloconfroot.bst"

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    assert result.exit_code == 0

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


# Test running an executable built with autotools
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_autotools_run(cli, datafiles):
    project = str(datafiles)
    element_name = "autotools/amhello.bst"

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["shell", element_name, "/usr/bin/hello"])
    assert result.exit_code == 0
    assert result.output == "Hello World!\nThis is amhello 1.0.\n"
