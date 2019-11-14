# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream.testing._utils.site import HAVE_SANDBOX, IS_LINUX


pytestmark = pytest.mark.integration

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


@pytest.mark.skipif(not IS_LINUX or HAVE_SANDBOX != "bwrap", reason="Only available on linux with bubblewrap")
@pytest.mark.datafiles(DATA_DIR)
def test_build_uid_overridden(cli, datafiles):
    project = str(datafiles)
    element_name = "build-uid/build-uid.bst"

    project_config = {"name": "build-uid-test", "sandbox": {"build-uid": 800, "build-gid": 900}}

    result = cli.run_project_config(project=project, project_config=project_config, args=["build", element_name])
    assert result.exit_code == 0


@pytest.mark.skipif(not IS_LINUX or HAVE_SANDBOX != "bwrap", reason="Only available on linux with bubbelwrap")
@pytest.mark.datafiles(DATA_DIR)
def test_build_uid_in_project(cli, datafiles):
    project = str(datafiles)
    element_name = "build-uid/build-uid-1023.bst"

    project_config = {"name": "build-uid-test", "sandbox": {"build-uid": 1023, "build-gid": 3490}}

    result = cli.run_project_config(project=project, project_config=project_config, args=["build", element_name])
    assert result.exit_code == 0


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(HAVE_SANDBOX != "bwrap", reason="Only available with a functioning sandbox")
def test_build_uid_default(cli, datafiles):
    project = str(datafiles)
    element_name = "build-uid/build-uid-default.bst"

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0
