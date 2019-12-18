# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream.testing._utils.site import IS_LINUX, MACHINE_ARCH, HAVE_SANDBOX


pytestmark = pytest.mark.integration
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "doc", "examples", "running-commands")


@pytest.mark.skipif(MACHINE_ARCH != "x86-64", reason="Examples are written for x86-64")
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not IS_LINUX or not HAVE_SANDBOX, reason="Only available on linux with sandbox")
def test_running_commands_build(cli, datafiles):
    project = str(datafiles)

    result = cli.run(project=project, args=["build", "hello.bst"])
    assert result.exit_code == 0


# Test running the executable
@pytest.mark.skipif(MACHINE_ARCH != "x86-64", reason="Examples are written for x86-64")
@pytest.mark.skipif(not IS_LINUX or not HAVE_SANDBOX, reason="Only available on linux with sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_running_commands_run(cli, datafiles):
    project = str(datafiles)

    result = cli.run(project=project, args=["build", "hello.bst"])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["shell", "hello.bst", "--", "hello"])
    assert result.exit_code == 0
    assert result.output == "Hello World\n"
