# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import cli_remote_execution as cli  # pylint: disable=unused-import
from buildstream.testing.integration import assert_contains


pytestmark = pytest.mark.remotecache


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")

# Test building an executable with a remote cache:
@pytest.mark.datafiles(DATA_DIR)
def test_remote_autotools_build(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    element_name = "autotools/amhello.bst"

    result = cli.run(project=project, args=["build", element_name])
    result.assert_success()
    assert element_name in result.get_pushed_elements()

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

    # then remove it locally
    result = cli.run(project=project, args=["artifact", "delete", element_name])
    result.assert_success()

    result = cli.run(project=project, args=["build", element_name])
    result.assert_success()
    assert element_name in result.get_pulled_elements()


# Test building an executable with a remote cache:
@pytest.mark.datafiles(DATA_DIR)
def test_remote_autotools_build_no_cache(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    element_name = "autotools/amhello.bst"

    cli.configure({"artifacts": {"url": "http://fake.url.service", "push": True}})
    result = cli.run(project=project, args=["build", element_name])
    result.assert_success()

    assert """WARNING Failed to initialize remote""" in result.stderr
    assert """Remote initialisation failed with status UNAVAILABLE: DNS resolution failed""" in result.stderr
