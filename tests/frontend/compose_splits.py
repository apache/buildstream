# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest
from buildstream.testing.runcli import cli  # pylint: disable=unused-import

# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project",)


@pytest.mark.parametrize("target", [("compose-include-bin.bst"), ("compose-exclude-dev.bst")])
@pytest.mark.datafiles(DATA_DIR)
def test_compose_splits(datafiles, cli, target):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")

    # First build it
    result = cli.run(project=project, args=["build", target])
    result.assert_success()

    # Now check it out
    result = cli.run(project=project, args=["artifact", "checkout", target, "--directory", checkout])
    result.assert_success()

    # Check that the executable hello file is found in the checkout
    filename = os.path.join(checkout, "usr", "bin", "hello")
    assert os.path.exists(filename)

    # Check that the executable hello file is found in the checkout
    filename = os.path.join(checkout, "usr", "include", "pony.h")
    assert not os.path.exists(filename)
