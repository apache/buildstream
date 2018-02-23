import io
import os
import sys
import pytest

from buildstream import _yaml

from tests.testutils import cli_integration as cli
from tests.testutils.integration import walk_dir


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


# Test that staging a file inside a directory symlink works as expected.
#
# Regression test for https://gitlab.com/BuildStream/buildstream/issues/270
@pytest.mark.datafiles(DATA_DIR)
def test_compose_symlinks(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_path = os.path.join(project, 'elements')

    # Symlinks do not survive being placed in a source distribution
    # ('setup.py sdist'), so we have to create the one we need here.
    project_files = os.path.join(project, 'files', 'compose-symlinks', 'base')
    symlink_file = os.path.join(project_files, 'sbin')
    os.symlink(os.path.join('usr', 'sbin'), symlink_file, target_is_directory=True)

    result = cli.run(project=project, args=['build', 'compose-symlinks/compose.bst'])
    result.assert_success()

    result = cli.run(project=project, args=['checkout', 'compose-symlinks/compose.bst', checkout])
    result.assert_success()

    assert set(walk_dir(checkout)) == set(['/sbin', '/usr', '/usr/sbin',
                                           '/usr/sbin/init', '/usr/sbin/dummy'])
