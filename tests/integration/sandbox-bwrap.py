# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.exceptions import ErrorDomain

from buildstream.testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream.testing._utils.site import HAVE_SANDBOX, HAVE_BWRAP_JSON_STATUS


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


# Bubblewrap sandbox doesn't remove the dirs it created during its execution,
# so BuildStream tries to remove them to do good. BuildStream should be extra
# careful when those folders already exist and should not touch them, though.
@pytest.mark.skipif(HAVE_SANDBOX != "bwrap", reason="Only available with bubblewrap")
@pytest.mark.datafiles(DATA_DIR)
def test_sandbox_bwrap_cleanup_build(cli, datafiles):
    project = str(datafiles)
    # This element depends on a base image with non-empty `/tmp` folder.
    element_name = "sandbox-bwrap/test-cleanup.bst"

    # Here, BuildStream should not attempt any rmdir etc.
    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0


@pytest.mark.skipif(HAVE_SANDBOX != "bwrap", reason="Only available with bubblewrap")
@pytest.mark.skipif(not HAVE_BWRAP_JSON_STATUS, reason="Only available with bubblewrap supporting --json-status-fd")
@pytest.mark.datafiles(DATA_DIR)
def test_sandbox_bwrap_distinguish_setup_error(cli, datafiles):
    project = str(datafiles)
    element_name = "sandbox-bwrap/non-executable-shell.bst"

    result = cli.run(project=project, args=["build", element_name])
    result.assert_task_error(error_domain=ErrorDomain.SANDBOX, error_reason="bwrap-sandbox-fail")


@pytest.mark.skipif(HAVE_SANDBOX != "bwrap", reason="Only available with bubblewrap")
@pytest.mark.datafiles(DATA_DIR)
def test_sandbox_bwrap_return_subprocess(cli, datafiles):
    project = str(datafiles)
    element_name = "sandbox-bwrap/command-exit-42.bst"

    cli.configure(
        {"logging": {"message-format": "%{element}|%{message}",},}
    )

    result = cli.run(project=project, args=["build", element_name])
    result.assert_task_error(error_domain=ErrorDomain.SANDBOX, error_reason="command-failed")
    assert "sandbox-bwrap/command-exit-42.bst|Command failed with exitcode 42" in result.stderr
