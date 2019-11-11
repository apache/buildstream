# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream.testing.integration import assert_contains
from buildstream.testing._utils.site import IS_LINUX


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "doc", "examples", "first-project")


@pytest.mark.skipif(not IS_LINUX, reason="Only available on linux")
@pytest.mark.datafiles(DATA_DIR)
def test_first_project_build_checkout(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")

    result = cli.run(project=project, args=["build", "hello.bst"])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["artifact", "checkout", "hello.bst", "--directory", checkout])
    assert result.exit_code == 0

    assert_contains(checkout, ["/hello.world"])
