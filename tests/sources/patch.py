import os
import pytest

from buildstream._exceptions import ErrorDomain
from tests.testutils import cli

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'patch',
)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_missing_patch(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # Removing the local file causes preflight to fail
    localfile = os.path.join(datafiles.dirname, datafiles.basename, 'file_1.patch')
    os.remove(localfile)

    result = cli.run(project=project, args=[
        'show', 'target.bst'
    ])
    result.assert_main_error(ErrorDomain.SOURCE, 'patch-no-exist')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_non_regular_file_patch(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # Add a fifo, that's not a regular file, should cause explosions
    patch_path = os.path.join(datafiles.dirname, datafiles.basename, 'irregular_file.patch')
    os.mkfifo(patch_path)

    result = cli.run(project=project, args=[
        'show', 'irregular.bst'
    ])
    result.assert_main_error(ErrorDomain.SOURCE, "patch-not-a-file")


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_stage_and_patch(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    result.assert_success()

    # Test the file.txt was patched and changed
    with open(os.path.join(checkoutdir, 'file.txt')) as f:
        assert(f.read() == 'This is text file with superpowers\n')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_stage_file_nonexistent_dir(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Fails at build time because it tries to patch into a non-existing directory
    result = cli.run(project=project, args=['build', 'failure-nonexistent-dir.bst'])
    result.assert_main_error(ErrorDomain.PIPELINE, None)
    result.assert_task_error(ErrorDomain.SOURCE, "patch-no-files")


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_stage_file_empty_dir(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Fails at build time because it tries to patch with nothing else staged
    result = cli.run(project=project, args=['build', 'failure-empty-dir.bst'])
    result.assert_main_error(ErrorDomain.PIPELINE, None)
    result.assert_task_error(ErrorDomain.SOURCE, "patch-no-files")


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'separate-patch-dir'))
def test_stage_separate_patch_dir(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Track, fetch, build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    result.assert_success()

    # Test the file.txt was patched and changed
    with open(os.path.join(checkoutdir, 'test-dir', 'file.txt')) as f:
        assert(f.read() == 'This is text file in a directory with superpowers\n')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'multiple-patches'))
def test_stage_multiple_patches(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Track, fetch, build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    result.assert_success()

    # Test the file.txt was patched and changed
    with open(os.path.join(checkoutdir, 'file.txt')) as f:
        assert(f.read() == 'This is text file with more superpowers\n')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'different-strip-level'))
def test_patch_strip_level(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Track, fetch, build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    result.assert_success()

    # Test the file.txt was patched and changed
    with open(os.path.join(checkoutdir, 'file.txt')) as f:
        assert(f.read() == 'This is text file with superpowers\n')
