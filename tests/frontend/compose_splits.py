import os
import pytest
from tests.testutils.runcli import cli

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


@pytest.mark.parametrize("target", [
    ('compose-include-bin.bst'),
    ('compose-exclude-dev.bst')
])
@pytest.mark.datafiles(DATA_DIR)
def test_compose_splits(datafiles, cli, target):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')

    # First build it
    result = cli.run(project=project, args=['build', target])
    result.assert_success()

    # Now check it out
    result = cli.run(project=project, args=[
        'checkout', target, checkout
    ])
    result.assert_success()

    # Check that the executable hello file is found in the checkout
    filename = os.path.join(checkout, 'usr', 'bin', 'hello')
    assert os.path.exists(filename)

    # Check that the executable hello file is found in the checkout
    filename = os.path.join(checkout, 'usr', 'include', 'pony.h')
    assert not os.path.exists(filename)
