# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.exceptions import ErrorDomain

from buildstream.testing import cli  # pylint: disable=unused-import


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "missing-command")


@pytest.mark.datafiles(DATA_DIR)
def test_missing_command(cli, datafiles):
    project = str(datafiles)
    result = cli.run(project=project, args=["build", "no-runtime.bst"])
    result.assert_task_error(ErrorDomain.SANDBOX, "missing-command")
    assert cli.get_element_state(project, "no-runtime.bst") == "failed"
