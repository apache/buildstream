# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream.testing.integration import assert_contains
from buildstream.testing._utils.site import IS_LINUX, MACHINE_ARCH, HAVE_SANDBOX
import tests.testutils.patch as patch

pytestmark = pytest.mark.integration

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "doc", "examples", "developing")


# Test that the project builds successfully
@pytest.mark.skipif(MACHINE_ARCH != "x86-64", reason="Examples are written for x86-64")
@pytest.mark.skipif(not IS_LINUX or not HAVE_SANDBOX, reason="Only available on linux with SANDBOX")
@pytest.mark.datafiles(DATA_DIR)
def test_autotools_build(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")

    # Check that the project can be built correctly.
    result = cli.run(project=project, args=["build", "hello.bst"])
    result.assert_success()

    result = cli.run(project=project, args=["artifact", "checkout", "hello.bst", "--directory", checkout])
    result.assert_success()

    assert_contains(checkout, ["/usr", "/usr/lib", "/usr/bin", "/usr/share", "/usr/bin/hello"])


# Test the unmodified hello command works as expected.
@pytest.mark.skipif(MACHINE_ARCH != "x86-64", reason="Examples are written for x86-64")
@pytest.mark.skipif(not IS_LINUX or not HAVE_SANDBOX, reason="Only available on linux with SANDBOX")
@pytest.mark.datafiles(DATA_DIR)
def test_run_unmodified_hello(cli, datafiles):
    project = str(datafiles)

    result = cli.run(project=project, args=["build", "hello.bst"])
    result.assert_success()

    result = cli.run(project=project, args=["shell", "hello.bst", "hello"])
    result.assert_success()
    assert result.output == "Hello World\n"


# Test opening a workspace
@pytest.mark.skipif(not IS_LINUX, reason="Only available on linux")
@pytest.mark.datafiles(DATA_DIR)
def test_open_workspace(cli, tmpdir, datafiles):
    project = str(datafiles)
    workspace_dir = os.path.join(str(tmpdir), "workspace_hello")

    result = cli.run(project=project, args=["workspace", "open", "-f", "--directory", workspace_dir, "hello.bst",])
    result.assert_success()

    result = cli.run(project=project, args=["workspace", "list"])
    result.assert_success()

    result = cli.run(project=project, args=["workspace", "close", "--remove-dir", "hello.bst"])
    result.assert_success()


# Test making a change using the workspace
@pytest.mark.skipif(MACHINE_ARCH != "x86-64", reason="Examples are written for x86-64")
@pytest.mark.skipif(not IS_LINUX or not HAVE_SANDBOX, reason="Only available on linux with SANDBOX")
@pytest.mark.datafiles(DATA_DIR)
def test_make_change_in_workspace(cli, tmpdir, datafiles):
    project = str(datafiles)
    workspace_dir = os.path.join(str(tmpdir), "workspace_hello")

    result = cli.run(project=project, args=["workspace", "open", "-f", "--directory", workspace_dir, "hello.bst"])
    result.assert_success()

    result = cli.run(project=project, args=["workspace", "list"])
    result.assert_success()

    patch_target = os.path.join(workspace_dir, "hello.c")
    patch_source = os.path.join(project, "update.patch")
    patch.apply(patch_target, patch_source)

    result = cli.run(project=project, args=["build", "hello.bst"])
    result.assert_success()

    result = cli.run(project=project, args=["shell", "hello.bst", "--", "hello"])
    result.assert_success()
    assert result.output == "Hello World\nWe can use workspaces!\n"

    result = cli.run(project=project, args=["workspace", "close", "--remove-dir", "hello.bst"])
    result.assert_success()
