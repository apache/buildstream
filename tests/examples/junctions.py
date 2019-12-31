# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream.testing._utils.site import IS_LINUX, MACHINE_ARCH, HAVE_SANDBOX

pytestmark = pytest.mark.integration

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "doc", "examples", "junctions")


# Test that the project builds successfully
@pytest.mark.skipif(MACHINE_ARCH != "x86-64", reason="Examples are written for x86-64")
@pytest.mark.skipif(not IS_LINUX or not HAVE_SANDBOX, reason="Only available on linux with bubblewrap")
@pytest.mark.datafiles(DATA_DIR)
def test_build(cli, datafiles):
    project = str(datafiles)

    result = cli.run(project=project, args=["build", "callHello.bst"])
    result.assert_success()


# Test the callHello script works as expected.
@pytest.mark.skipif(MACHINE_ARCH != "x86-64", reason="Examples are written for x86-64")
@pytest.mark.skipif(not IS_LINUX or not HAVE_SANDBOX, reason="Only available on linux with bubblewrap")
@pytest.mark.datafiles(DATA_DIR)
def test_shell_call_hello(cli, datafiles):
    project = str(datafiles)

    result = cli.run(project=project, args=["build", "callHello.bst"])
    result.assert_success()

    result = cli.run(project=project, args=["shell", "callHello.bst", "--", "/bin/sh", "callHello.sh"])
    result.assert_success()
    assert result.output == "Calling hello:\nHello World!\nThis is amhello 1.0.\n"


# Test opening a cross-junction workspace
@pytest.mark.skipif(not IS_LINUX, reason="Only available on linux")
@pytest.mark.datafiles(DATA_DIR)
def test_open_cross_junction_workspace(cli, tmpdir, datafiles):
    project = str(datafiles)
    workspace_dir = os.path.join(str(tmpdir), "workspace_hello_junction")

    result = cli.run(
        project=project, args=["workspace", "open", "--directory", workspace_dir, "hello-junction.bst:hello.bst"]
    )
    result.assert_success()

    result = cli.run(project=project, args=["workspace", "close", "--remove-dir", "hello-junction.bst:hello.bst"])
    result.assert_success()
