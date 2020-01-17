# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.exceptions import ErrorDomain
from buildstream.testing import cli_remote_execution as cli  # pylint: disable=unused-import
from buildstream.testing.integration import assert_contains

from tests.testutils.artifactshare import create_artifact_share


pytestmark = pytest.mark.remoteexecution


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


# Test that `bst build` does not download file blobs of a build-only dependency
# to the local cache.
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("pull_artifact_files", [True, False])
@pytest.mark.parametrize("build_all", [True, False])
def test_build_dependency_partial_local_cas(cli, datafiles, pull_artifact_files, build_all):
    project = str(datafiles)
    element_name = "no-runtime-deps.bst"
    builddep_element_name = "autotools/amhello.bst"
    checkout = os.path.join(cli.directory, "checkout")
    builddep_checkout = os.path.join(cli.directory, "builddep-checkout")

    services = cli.ensure_services()
    assert set(services) == set(["action-cache", "execution", "storage"])

    # configure pull blobs
    if build_all:
        cli.configure({"build": {"dependencies": "all"}})
    cli.config["remote-execution"]["pull-artifact-files"] = pull_artifact_files

    result = cli.run(project=project, args=["build", element_name])
    result.assert_success()

    # Verify artifact is pulled bar files when ensure artifact files is set
    result = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    if pull_artifact_files:
        result.assert_success()
        assert_contains(checkout, ["/test"])
    else:
        result.assert_main_error(ErrorDomain.STREAM, "uncached-checkout-attempt")

    # Verify build dependencies is pulled for ALL and BUILD
    result = cli.run(
        project=project, args=["artifact", "checkout", builddep_element_name, "--directory", builddep_checkout]
    )
    if build_all and pull_artifact_files:
        result.assert_success()
    else:
        result.assert_main_error(ErrorDomain.STREAM, "uncached-checkout-attempt")


@pytest.mark.datafiles(DATA_DIR)
def test_build_partial_push(cli, tmpdir, datafiles):
    project = str(datafiles)
    share_dir = os.path.join(str(tmpdir), "artifactshare")
    element_name = "no-runtime-deps.bst"
    builddep_element_name = "autotools/amhello.bst"

    with create_artifact_share(share_dir) as share:

        services = cli.ensure_services()
        assert set(services) == set(["action-cache", "execution", "storage"])

        cli.config["artifacts"] = {
            "url": share.repo,
            "push": True,
        }

        res = cli.run(project=project, args=["build", element_name])
        res.assert_success()

        assert builddep_element_name in res.get_pushed_elements()
