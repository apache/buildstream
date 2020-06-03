# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os

import pytest

from buildstream import utils, _yaml
from buildstream.exceptions import ErrorDomain
from buildstream.testing._utils.site import IS_LINUX
from buildstream.testing import cli  # pylint: disable=unused-import


# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "missing-dependencies",)


def _symlink_host_tools_to_dir(host_tools, dir_):
    dir_.mkdir(exist_ok=True)
    for tool in host_tools:
        target_path = dir_ / tool
        os.symlink(utils.get_host_tool(tool), str(target_path))


@pytest.mark.skipif(not IS_LINUX, reason="Only available on Linux")
@pytest.mark.datafiles(DATA_DIR)
def test_missing_buildbox_run_has_nice_error_message(cli, datafiles, tmp_path):
    # Create symlink to buildbox-casd and git to work with custom PATH
    bin_dir = tmp_path / "bin"
    _symlink_host_tools_to_dir(["buildbox-casd", "git"], bin_dir)

    project = str(datafiles)
    element_path = os.path.join(project, "elements", "element.bst")

    # Write out our test target
    element = {
        "kind": "script",
        "depends": [{"filename": "base.bst", "type": "build",},],
        "config": {"commands": ["false",],},
    }
    _yaml.roundtrip_dump(element, element_path)

    # Build without access to host tools, this should fail with a nice error
    result = cli.run(project=project, args=["build", "element.bst"], env={"PATH": str(bin_dir)})
    result.assert_task_error(ErrorDomain.SANDBOX, "unavailable-local-sandbox")
    assert "not found" in result.stderr
