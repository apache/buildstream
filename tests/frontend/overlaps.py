import os
import pytest
from tests.testutils.runcli import cli

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "overlaps"
)


@pytest.mark.datafiles(DATA_DIR)
def test_overlaps(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "basic")
    result = cli.run(project=project, silent=True, args=[
        'build', 'collect.bst'])

    result.assert_success()
    assert "/file1: three.bst above one.bst" in result.stderr
    assert "/file2: two.bst above three.bst above one.bst" in result.stderr
    assert "/file3: two.bst above three.bst" in result.stderr
