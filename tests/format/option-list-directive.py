# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest
from buildstream.testing.runcli import cli  # pylint: disable=unused-import

# Project directory
DATA_DIR = os.path.dirname(os.path.realpath(__file__))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("mount_devices", [("true"), ("false")])
def test_override(cli, datafiles, mount_devices):
    project = os.path.join(datafiles.dirname, datafiles.basename, "option-list-directive")

    bst_args = ["--option", "shell_mount_devices", mount_devices, "build"]
    result = cli.run(project=project, silent=True, args=bst_args)
    result.assert_success()
