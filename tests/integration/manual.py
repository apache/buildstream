# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream import _yaml

from buildstream.testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream.testing._utils.site import HAVE_SANDBOX


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


def create_manual_element(name, path, config, variables, environment):
    element = {
        "kind": "manual",
        "depends": [{"filename": "base.bst", "type": "build"}],
        "config": config,
        "variables": variables,
        "environment": environment,
    }
    os.makedirs(os.path.dirname(os.path.join(path, name)), exist_ok=True)
    _yaml.roundtrip_dump(element, os.path.join(path, name))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_manual_element(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    element_path = os.path.join(project, "elements")
    element_name = "import/import.bst"

    create_manual_element(
        element_name,
        element_path,
        {
            "configure-commands": ["echo './configure' >> test"],
            "build-commands": ["echo 'make' >> test"],
            "install-commands": ["echo 'make install' >> test", "cp test %{install-root}"],
            "strip-commands": ["echo 'strip' >> %{install-root}/test"],
        },
        {},
        {},
    )

    res = cli.run(project=project, args=["build", element_name])
    assert res.exit_code == 0

    cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    assert res.exit_code == 0

    with open(os.path.join(checkout, "test")) as f:
        text = f.read()

    assert (
        text
        == """./configure
make
make install
strip
"""
    )


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_manual_element_environment(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    element_path = os.path.join(project, "elements")
    element_name = "import/import.bst"

    create_manual_element(
        element_name, element_path, {"install-commands": ["echo $V >> test", "cp test %{install-root}"]}, {}, {"V": 2}
    )

    res = cli.run(project=project, args=["build", element_name])
    assert res.exit_code == 0

    cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    assert res.exit_code == 0

    with open(os.path.join(checkout, "test")) as f:
        text = f.read()

    assert text == "2\n"


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_manual_element_noparallel(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    element_path = os.path.join(project, "elements")
    element_name = "import/import.bst"

    create_manual_element(
        element_name,
        element_path,
        {"install-commands": ["echo $MAKEFLAGS >> test", "echo $V >> test", "cp test %{install-root}"]},
        {"notparallel": True},
        {"MAKEFLAGS": "-j%{max-jobs} -Wall", "V": 2},
    )

    res = cli.run(project=project, args=["build", element_name])
    assert res.exit_code == 0

    cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    assert res.exit_code == 0

    with open(os.path.join(checkout, "test")) as f:
        text = f.read()

    assert (
        text
        == """-j1 -Wall
2
"""
    )


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_manual_element_logging(cli, datafiles):
    project = str(datafiles)
    element_path = os.path.join(project, "elements")
    element_name = "import/import.bst"

    create_manual_element(
        element_name,
        element_path,
        {
            "configure-commands": ["echo configure"],
            "build-commands": ["echo build"],
            "install-commands": ["echo install"],
            "strip-commands": ["echo strip"],
        },
        {},
        {},
    )

    res = cli.run(project=project, args=["build", element_name])
    assert res.exit_code == 0

    # Verify that individual commands are logged
    assert "echo configure" in res.stderr
    assert "echo build" in res.stderr
    assert "echo install" in res.stderr
    assert "echo strip" in res.stderr
