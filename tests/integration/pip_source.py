# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream import _yaml

from buildstream.testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream.testing.integration import assert_contains
from buildstream.testing._utils.site import HAVE_SANDBOX

from tests.testutils.python_repo import setup_pypi_repo  # pylint: disable=unused-import


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


@pytest.mark.datafiles(DATA_DIR)
def test_pip_source_import_packages(cli, datafiles, setup_pypi_repo):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    element_path = os.path.join(project, "elements")
    element_name = "pip/hello.bst"

    # check that exotically named packages are imported correctly
    myreqs_packages = "hellolib"
    dependencies = ["app2", "app.3", "app-4", "app_5", "app.no.6", "app-no-7", "app_no_8"]
    mock_packages = {myreqs_packages: {package: {} for package in dependencies}}

    # create mock pypi repository
    pypi_repo = os.path.join(project, "files", "pypi-repo")
    os.makedirs(pypi_repo, exist_ok=True)
    setup_pypi_repo(mock_packages, pypi_repo)

    element = {
        "kind": "import",
        "sources": [
            {"kind": "local", "path": "files/pip-source"},
            {"kind": "pip", "url": "file://{}".format(os.path.realpath(pypi_repo)), "packages": [myreqs_packages]},
        ],
    }
    os.makedirs(os.path.dirname(os.path.join(element_path, element_name)), exist_ok=True)
    _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

    result = cli.run(project=project, args=["source", "track", element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    assert result.exit_code == 0

    assert_contains(
        checkout,
        [
            "/.bst_pip_downloads",
            "/.bst_pip_downloads/hellolib-0.1.tar.gz",
            "/.bst_pip_downloads/app2-0.1.tar.gz",
            "/.bst_pip_downloads/app.3-0.1.tar.gz",
            "/.bst_pip_downloads/app-4-0.1.tar.gz",
            "/.bst_pip_downloads/app_5-0.1.tar.gz",
            "/.bst_pip_downloads/app.no.6-0.1.tar.gz",
            "/.bst_pip_downloads/app-no-7-0.1.tar.gz",
            "/.bst_pip_downloads/app_no_8-0.1.tar.gz",
        ],
    )


@pytest.mark.datafiles(DATA_DIR)
def test_pip_source_import_requirements_files(cli, datafiles, setup_pypi_repo):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    element_path = os.path.join(project, "elements")
    element_name = "pip/hello.bst"

    # check that exotically named packages are imported correctly
    myreqs_packages = "hellolib"
    dependencies = ["app2", "app.3", "app-4", "app_5", "app.no.6", "app-no-7", "app_no_8"]
    mock_packages = {myreqs_packages: {package: {} for package in dependencies}}

    # create mock pypi repository
    pypi_repo = os.path.join(project, "files", "pypi-repo")
    os.makedirs(pypi_repo, exist_ok=True)
    setup_pypi_repo(mock_packages, pypi_repo)

    element = {
        "kind": "import",
        "sources": [
            {"kind": "local", "path": "files/pip-source"},
            {
                "kind": "pip",
                "url": "file://{}".format(os.path.realpath(pypi_repo)),
                "requirements-files": ["myreqs.txt"],
            },
        ],
    }
    os.makedirs(os.path.dirname(os.path.join(element_path, element_name)), exist_ok=True)
    _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

    result = cli.run(project=project, args=["source", "track", element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    assert result.exit_code == 0

    assert_contains(
        checkout,
        [
            "/.bst_pip_downloads",
            "/.bst_pip_downloads/hellolib-0.1.tar.gz",
            "/.bst_pip_downloads/app2-0.1.tar.gz",
            "/.bst_pip_downloads/app.3-0.1.tar.gz",
            "/.bst_pip_downloads/app-4-0.1.tar.gz",
            "/.bst_pip_downloads/app_5-0.1.tar.gz",
            "/.bst_pip_downloads/app.no.6-0.1.tar.gz",
            "/.bst_pip_downloads/app-no-7-0.1.tar.gz",
            "/.bst_pip_downloads/app_no_8-0.1.tar.gz",
        ],
    )


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_pip_source_build(cli, datafiles, setup_pypi_repo):
    project = str(datafiles)
    element_path = os.path.join(project, "elements")
    element_name = "pip/hello.bst"

    # check that exotically named packages are imported correctly
    myreqs_packages = "hellolib"
    dependencies = ["app2", "app.3", "app-4", "app_5", "app.no.6", "app-no-7", "app_no_8"]
    mock_packages = {myreqs_packages: {package: {} for package in dependencies}}

    # create mock pypi repository
    pypi_repo = os.path.join(project, "files", "pypi-repo")
    os.makedirs(pypi_repo, exist_ok=True)
    setup_pypi_repo(mock_packages, pypi_repo)

    element = {
        "kind": "manual",
        "depends": ["base.bst"],
        "sources": [
            {"kind": "local", "path": "files/pip-source"},
            {
                "kind": "pip",
                "url": "file://{}".format(os.path.realpath(pypi_repo)),
                "requirements-files": ["myreqs.txt"],
                "packages": dependencies,
            },
        ],
        "config": {
            "install-commands": [
                "pip3 install --no-index --prefix %{install-root}/usr .bst_pip_downloads/*.tar.gz",
                "install app1.py %{install-root}/usr/bin/",
            ]
        },
    }
    os.makedirs(os.path.dirname(os.path.join(element_path, element_name)), exist_ok=True)
    _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

    result = cli.run(project=project, args=["source", "track", element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["shell", element_name, "/usr/bin/app1.py"])
    assert result.exit_code == 0
    assert result.output == "Hello App1! This is hellolib\n"
