# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest
from buildstream.testing import cli  # pylint: disable=unused-import


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project", "default")


# Test that output is formatted correctly, when there are multiple matches of a
# variable that is known to BuildStream.
#
@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_match_multiple(cli, datafiles):
    project = str(datafiles)
    result = cli.run(project=project, args=["show", "--format", "%{name} {name} %{name}", "manual.bst"])
    result.assert_success()
    assert result.output == "manual.bst {name} manual.bst\n"
