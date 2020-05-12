# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os

import pytest

from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream.testing.runcli import cli  # pylint: disable=unused-import


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "variables")


@pytest.mark.datafiles(DATA_DIR)
def test_variables_are_resolved(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected file
    assert os.path.exists(os.path.join(checkoutdir, "file.txt"))


@pytest.mark.datafiles(DATA_DIR)
def test_handles_unresolved_variables(cli, tmpdir, datafiles):
    project = str(datafiles)

    result = cli.run(project=project, args=["build", "unresolveable-target.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.UNRESOLVED_VARIABLE)
