import os
import pytest

from buildstream._pipeline import PipelineError
from buildstream import SourceError
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
    assert result.exit_code != 0
    assert result.exception
    assert isinstance(result.exception, SourceError)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_stage_and_patch(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    assert result.exit_code == 0
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    assert result.exit_code == 0

    # Test the file.txt was patched and changed
    with open(os.path.join(checkoutdir, 'file.txt')) as f:
        assert(f.read() == 'This is text file with superpowers\n')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_stage_file_nonexistent_dir(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Fails at build time because it tries to patch into a non-existing directory
    result = cli.run(project=project, args=['build', 'failure-nonexistent-dir.bst'])
    assert result.exit_code != 0
    assert result.exception
    assert isinstance(result.exception, PipelineError)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_stage_file_empty_dir(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Fails at build time because it tries to patch with nothing else staged
    result = cli.run(project=project, args=['build', 'failure-empty-dir.bst'])
    assert result.exit_code != 0
    assert result.exception
    assert isinstance(result.exception, PipelineError)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'separate-patch-dir'))
def test_stage_separate_patch_dir(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Track, fetch, build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    assert result.exit_code == 0
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    assert result.exit_code == 0

    # Test the file.txt was patched and changed
    with open(os.path.join(checkoutdir, 'test-dir', 'file.txt')) as f:
        assert(f.read() == 'This is text file in a directory with superpowers\n')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'multiple-patches'))
def test_stage_multiple_patches(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Track, fetch, build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    assert result.exit_code == 0
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    assert result.exit_code == 0

    # Test the file.txt was patched and changed
    with open(os.path.join(checkoutdir, 'file.txt')) as f:
        assert(f.read() == 'This is text file with more superpowers\n')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'different-strip-level'))
def test_patch_strip_level(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Track, fetch, build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    assert result.exit_code == 0
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    assert result.exit_code == 0

    # Test the file.txt was patched and changed
    with open(os.path.join(checkoutdir, 'file.txt')) as f:
        assert(f.read() == 'This is text file with superpowers\n')
