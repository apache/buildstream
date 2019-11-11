# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream.testing._utils.site import HAVE_SANDBOX


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_stack(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    element_name = "stack/stack.bst"

    res = cli.run(project=project, args=["build", element_name])
    assert res.exit_code == 0

    cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    assert res.exit_code == 0

    with open(os.path.join(checkout, "hi")) as f:
        hi = f.read()

    with open(os.path.join(checkout, "another-hi")) as f:
        another_hi = f.read()

    assert hi == "Hi\n"
    assert another_hi == "Another hi\n"
