import os
import pytest

from buildstream._exceptions import ErrorDomain
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
    result.assert_main_error(ErrorDomain.SOURCE, None)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_stage_file(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected file
    assert(os.path.exists(os.path.join(checkoutdir, 'file.txt')))


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'directory'))
def test_stage_directory(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected file and directory and other file
    assert(os.path.exists(os.path.join(checkoutdir, 'file.txt')))
    assert(os.path.exists(os.path.join(checkoutdir, 'subdir', 'anotherfile.txt')))


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'symlink'))
def test_stage_symlink(cli, tmpdir, datafiles):

    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Workaround datafiles bug:
    #
    #   https://github.com/omarkohl/pytest-datafiles/issues/1
    #
    # Create the symlink by hand.
    symlink = os.path.join(project, 'files', 'symlink-to-file.txt')
    os.symlink('file.txt', symlink)

    # Build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected file and directory and other file
    assert(os.path.exists(os.path.join(checkoutdir, 'file.txt')))
    assert(os.path.exists(os.path.join(checkoutdir, 'symlink-to-file.txt')))
    assert(os.path.islink(os.path.join(checkoutdir, 'symlink-to-file.txt')))


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'file-exists'))
def test_stage_file_exists(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_main_error(ErrorDomain.STREAM, None)
    result.assert_task_error(ErrorDomain.SOURCE, 'ensure-stage-dir-fail')
