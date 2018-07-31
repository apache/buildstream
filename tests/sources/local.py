import os
import pytest

from buildstream._exceptions import ErrorDomain, LoadErrorReason
from tests.testutils import cli, filetypegenerator

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'local',
)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_missing_path(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # Removing the local file causes preflight to fail
    localfile = os.path.join(project, 'file.txt')
    os.remove(localfile)

    result = cli.run(project=project, args=[
        'show', 'target.bst'
    ])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_non_regular_file_or_directory(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    localfile = os.path.join(project, 'file.txt')

    for file_type in filetypegenerator.generate_file_types(localfile):
        result = cli.run(project=project, args=[
            'show', 'target.bst'
        ])
        if os.path.isdir(localfile) and not os.path.islink(localfile):
            result.assert_success()
        elif os.path.isfile(localfile) and not os.path.islink(localfile):
            result.assert_success()
        else:
            result.assert_main_error(ErrorDomain.LOAD,
                                     LoadErrorReason.PROJ_PATH_INVALID_KIND)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_invalid_absolute_path(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    with open(os.path.join(project, "target.bst"), 'r') as f:
        old_yaml = f.read()

    new_yaml = old_yaml.replace("file.txt", os.path.join(project, "file.txt"))
    assert old_yaml != new_yaml

    with open(os.path.join(project, "target.bst"), 'w') as f:
        f.write(new_yaml)

    result = cli.run(project=project, args=['show', 'target.bst'])
    result.assert_main_error(ErrorDomain.LOAD,
                             LoadErrorReason.PROJ_PATH_INVALID)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'invalid-relative-path'))
def test_invalid_relative_path(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    result = cli.run(project=project, args=['show', 'target.bst'])
    result.assert_main_error(ErrorDomain.LOAD,
                             LoadErrorReason.PROJ_PATH_INVALID)


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
