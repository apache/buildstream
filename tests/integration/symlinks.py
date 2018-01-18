import os
import shlex
import pytest

from buildstream import _yaml

from tests.testutils import cli_integration as cli
from tests.testutils.integration import assert_contains


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


@pytest.mark.datafiles(DATA_DIR)
def test_absolute_symlinks_made_relative(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_name = 'symlinks/dangling-symlink.bst'

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['checkout', element_name, checkout])
    assert result.exit_code == 0

    symlink = os.path.join(checkout, 'opt', 'orgname')
    assert os.path.islink(symlink)

    # The symlink is created to point to /usr/orgs/orgname, but BuildStream
    # should make all symlink target relative when assembling the artifact.
    # This is done so that nothing points outside the sandbox and so that
    # staging artifacts in locations other than / doesn't cause the links to
    # all break.
    assert os.readlink(symlink) == '../usr/orgs/orgname'


@pytest.mark.datafiles(DATA_DIR)
def test_allow_overlaps_inside_symlink_with_dangling_target(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_name = 'symlinks/dangling-symlink-overlap.bst'

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['checkout', element_name, checkout])
    assert result.exit_code == 0

    # See the dangling-symlink*.bst elements for details on what we are testing.
    assert_contains(checkout, ['/usr/orgs/orgname/etc/org.conf'])


@pytest.mark.datafiles(DATA_DIR)
def test_detect_symlink_overlaps_pointing_outside_sandbox(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_name = 'symlinks/symlink-to-outside-sandbox-overlap.bst'

    # Building the two elements should succeed...
    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    # ...but when we compose them together, the overlaps create paths that
    # point outside the sandbox which BuildStream needs to detect before it
    # tries to actually write there.
    result = cli.run(project=project, args=['checkout', element_name, checkout])
    assert result.exit_code == -1
    assert "Destination path resolves to a path outside of the staging area" in result.stderr
