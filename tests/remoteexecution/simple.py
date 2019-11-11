# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import cli_remote_execution as cli  # pylint: disable=unused-import
from buildstream.testing.integration import assert_contains


pytestmark = pytest.mark.remoteexecution


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


# Test building an executable with remote-execution:
@pytest.mark.datafiles(DATA_DIR)
def test_remote_autotools_build(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    element_name = "autotools/amhello.bst"

    services = cli.ensure_services()
    assert set(services) == set(["action-cache", "execution", "storage"])

    result = cli.run(project=project, args=["build", element_name])
    result.assert_success()

    result = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
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


# Test running an executable built with remote-execution:
@pytest.mark.datafiles(DATA_DIR)
def test_remote_autotools_run(cli, datafiles):
    project = str(datafiles)
    element_name = "autotools/amhello.bst"

    services = cli.ensure_services()
    assert set(services) == set(["action-cache", "execution", "storage"])

    services = cli.ensure_services()

    result = cli.run(project=project, args=["build", element_name])
    result.assert_success()

    result = cli.run(project=project, args=["shell", element_name, "/usr/bin/hello"])
    result.assert_success()
    assert result.output == "Hello World!\nThis is amhello 1.0.\n"
