#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import shutil
import pytest

from buildstream import _yaml

from buildstream._testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream._testing._utils.site import HAVE_SANDBOX


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


def create_manual_element(name, path, config, variables, environment, sources=None):
    element = {
        "kind": "manual",
        "depends": [{"filename": "base.bst", "type": "build"}],
        "config": config,
        "variables": variables,
        "environment": environment,
    }
    if sources:
        element["sources"] = sources
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

    res = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    assert res.exit_code == 0

    with open(os.path.join(checkout, "test"), encoding="utf-8") as f:
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

    res = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    assert res.exit_code == 0

    with open(os.path.join(checkout, "test"), encoding="utf-8") as f:
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

    res = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    assert res.exit_code == 0

    with open(os.path.join(checkout, "test"), encoding="utf-8") as f:
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


# Regression test for https://gitlab.com/BuildStream/buildstream/-/issues/1295.
#
# Test that the command-subdir variable works as expected.
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_manual_command_subdir(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    element_path = os.path.join(project, "elements")
    element_name = "manual/command-subdir.bst"
    sources = [{"kind": "local", "path": "files/manual-element/root"}]

    create_manual_element(
        element_name,
        element_path,
        {"install-commands": ["cp hello %{install-root}"]},
        {},
        {},
        sources=sources,
    )

    # First, verify that element builds, and has the correct expected output.
    result = cli.run(project=project, args=["build", element_name])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    result.assert_success()
    with open(os.path.join(checkout, "hello"), encoding="utf-8") as f:
        assert f.read() == "hello from root\n"

    # Now, change element configuration to have a different command-subdir.
    # This should result in a different cache key.
    create_manual_element(
        element_name,
        element_path,
        {"install-commands": ["cp hello %{install-root}"]},
        {"command-subdir": "subdir"},
        {},
        sources=sources,
    )

    # Verify that the element needs to be rebuilt.
    assert cli.get_element_state(project, element_name) == "buildable"

    # Finally, ensure that the variable actually takes effect.
    result = cli.run(project=project, args=["build", element_name])
    result.assert_success()
    shutil.rmtree(checkout)
    result = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    result.assert_success()
    with open(os.path.join(checkout, "hello"), encoding="utf-8") as f:
        assert f.read() == "hello from subdir\n"


# Test staging artifacts into subdirectories
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_manual_stage_custom(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")

    # Verify that the element builds, and has the correct expected output.
    result = cli.run(project=project, args=["build", "manual/manual-stage-custom.bst"])
    result.assert_success()
    result = cli.run(
        project=project, args=["artifact", "checkout", "manual/manual-stage-custom.bst", "--directory", checkout]
    )
    result.assert_success()

    with open(os.path.join(checkout, "test.txt"), encoding="utf-8") as f:
        assert f.read() == "This is another test\n"
