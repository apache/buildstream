# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os

import pytest

from buildstream import _yaml

from buildstream.testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream.testing.integration import assert_contains
from buildstream.testing._utils.site import HAVE_SANDBOX

from tests.testutils import setup_pypi_repo  # pylint: disable=unused-import


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_pip_build(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    element_path = os.path.join(project, "elements")
    element_name = "pip/hello.bst"

    element = {
        "kind": "pip",
        "variables": {"pip": "pip3"},
        "depends": [{"filename": "base.bst"}],
        "sources": [
            {
                "kind": "tar",
                "url": "file://{}/files/hello.tar.xz".format(project),
                "ref": "ad96570b552498807abec33c06210bf68378d854ced6753b77916c5ed517610d",
            }
        ],
    }
    os.makedirs(os.path.dirname(os.path.join(element_path, element_name)), exist_ok=True)
    _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    assert result.exit_code == 0

    assert_contains(checkout, ["/usr", "/usr/lib", "/usr/bin", "/usr/bin/hello", "/usr/lib/python3.6"])


# Test running an executable built with pip
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_pip_run(cli, datafiles):
    # Create and build our test element
    test_pip_build(cli, datafiles)

    project = str(datafiles)
    element_name = "pip/hello.bst"

    result = cli.run(project=project, args=["shell", element_name, "/usr/bin/hello"])
    assert result.exit_code == 0
    assert result.output == "Hello, world!\n"


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_pip_element_should_install_pip_deps(cli, datafiles, setup_pypi_repo):
    project = str(datafiles)
    elements_path = os.path.join(project, "elements")
    element_name = "pip/hello.bst"

    # check that exotically named packages are imported correctly
    myreqs_packages = "alohalib"
    dependencies = ["app2", "app.3", "app-4", "app_5", "app.no.6", "app-no-7", "app_no_8"]
    mock_packages = {myreqs_packages: {package: {} for package in dependencies}}

    # set up directories
    pypi_repo = os.path.join(project, "files", "pypi-repo")
    os.makedirs(pypi_repo, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.join(elements_path, element_name)), exist_ok=True)
    setup_pypi_repo(mock_packages, pypi_repo)

    # create pip element
    element = {
        "kind": "pip",
        "variables": {"pip": "pip3"},
        "depends": [{"filename": "base.bst"}],
        "sources": [
            {
                "kind": "tar",
                "url": "file://{}/files/hello.tar.xz".format(project),
                # FIXME: remove hardcoded ref once issue #1010 is closed
                "ref": "ad96570b552498807abec33c06210bf68378d854ced6753b77916c5ed517610d",
            },
            {"kind": "pip", "url": "file://{}".format(os.path.realpath(pypi_repo)), "packages": [myreqs_packages],},
        ],
    }
    _yaml.roundtrip_dump(element, os.path.join(elements_path, element_name))

    result = cli.run(project=project, args=["source", "track", element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0

    # get installed packages in sandbox
    installed_packages = set(
        cli.run(project=project, args=["shell", element_name, "pip3", "freeze"]).output.split("\n")
    )
    # compare with packages that are expected to be installed
    pip_source_packages = {package.replace("_", "-") + "==0.1" for package in dependencies + [myreqs_packages]}
    assert pip_source_packages.issubset(installed_packages)
