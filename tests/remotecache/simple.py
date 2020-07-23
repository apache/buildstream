# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import cli_remote_execution as cli  # pylint: disable=unused-import
from buildstream.testing.integration import assert_contains


pytestmark = pytest.mark.remotecache


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")
DATA_DIR_NOCACHE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project_nocache")


# Test building an executable with a remote cache:
@pytest.mark.datafiles(DATA_DIR)
def test_remote_autotools_build(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    element_name = "autotools/amhello.bst"

    #    services = cli.ensure_services()
    #   assert set(services) == set(["action-cache", "execution", "storage"])

    result = cli.run(project=project, args=["build", element_name])
    result.assert_success()
    assert "INFO    Pushed artifact" in result.stderr

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
    assert "INFO    Pulled artifact" in result.stderr


# Test building an executable with a remote cache:
@pytest.mark.datafiles(DATA_DIR_NOCACHE)
def test_remote_autotools_build_no_cache(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    element_name = "autotools/amhello.bst"

    env = os.environ.copy()
    env["ARTIFACT_CACHE_SERVICE"] = "http://fake.url.service"
    result = cli.run(project=project, args=["build", element_name], env=env)
    result.assert_success()

    assert (
        """[--:--:--][        ][    main:core activity                 ] WARNING Failed to initialize remote"""
        in result.stderr
    )
    assert (
        """Remote initialisation failed with status UNAVAILABLE: failed to connect to all addresses""" in result.stderr
    )
