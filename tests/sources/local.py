import os
import pytest

from buildstream import SourceError
from tests.testutils import cli

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'local',
)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_missing_file(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # Removing the local file causes preflight to fail
    localfile = os.path.join(datafiles.dirname, datafiles.basename, 'file.txt')
    os.remove(localfile)

    result = cli.run(project=project, args=[
        'show', 'target.bst'
    ])
    assert result.exit_code != 0
    assert result.exception
    assert isinstance(result.exception, SourceError)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_stage_file(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    assert result.exit_code == 0
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    assert result.exit_code == 0

    # Check that the checkout contains the expected file
    assert(os.path.exists(os.path.join(checkoutdir, 'file.txt')))


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'directory'))
def test_stage_directory(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    assert result.exit_code == 0
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    assert result.exit_code == 0

    # Check that the checkout contains the expected file and directory and other file
    assert(os.path.exists(os.path.join(checkoutdir, 'file.txt')))
    assert(os.path.exists(os.path.join(checkoutdir, 'subdir', 'anotherfile.txt')))
