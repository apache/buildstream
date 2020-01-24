# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream.testing import cli  # pylint: disable=unused-import
from tests.testutils import filetypegenerator

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "patch",)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_missing_patch(cli, datafiles):
    project = str(datafiles)

    # Removing the local file causes preflight to fail
    localfile = os.path.join(project, "file_1.patch")
    os.remove(localfile)

    result = cli.run(project=project, args=["show", "target.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_non_regular_file_patch(cli, datafiles):
    project = str(datafiles)

    patch_path = os.path.join(project, "irregular_file.patch")
    for _file_type in filetypegenerator.generate_file_types(patch_path):
        result = cli.run(project=project, args=["show", "irregular.bst"])
        if os.path.isfile(patch_path) and not os.path.islink(patch_path):
            result.assert_success()
        else:
            result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.PROJ_PATH_INVALID_KIND)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_invalid_absolute_path(cli, datafiles):
    project = str(datafiles)

    with open(os.path.join(project, "target.bst"), "r") as f:
        old_yaml = f.read()
    new_yaml = old_yaml.replace("file_1.patch", os.path.join(project, "file_1.patch"))
    assert old_yaml != new_yaml

    with open(os.path.join(project, "target.bst"), "w") as f:
        f.write(new_yaml)

    result = cli.run(project=project, args=["show", "target.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.PROJ_PATH_INVALID)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "invalid-relative-path"))
def test_invalid_relative_path(cli, datafiles):
    project = str(datafiles)

    result = cli.run(project=project, args=["show", "irregular.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.PROJ_PATH_INVALID)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_stage_and_patch(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Test the file.txt was patched and changed
    with open(os.path.join(checkoutdir, "file.txt")) as f:
        assert f.read() == "This is text file with superpowers\n"


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_stage_file_nonexistent_dir(cli, datafiles):
    project = str(datafiles)

    # Fails at build time because it tries to patch into a non-existing directory
    result = cli.run(project=project, args=["build", "failure-nonexistent-dir.bst"])
    result.assert_main_error(ErrorDomain.STREAM, None)
    result.assert_task_error(ErrorDomain.SOURCE, "patch-no-files")


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_stage_file_empty_dir(cli, datafiles):
    project = str(datafiles)

    # Fails at build time because it tries to patch with nothing else staged
    result = cli.run(project=project, args=["build", "failure-empty-dir.bst"])
    result.assert_main_error(ErrorDomain.STREAM, None)
    result.assert_task_error(ErrorDomain.SOURCE, "patch-no-files")


@pytest.mark.datafiles(os.path.join(DATA_DIR, "separate-patch-dir"))
def test_stage_separate_patch_dir(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Track, fetch, build, checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Test the file.txt was patched and changed
    with open(os.path.join(checkoutdir, "test-dir", "file.txt")) as f:
        assert f.read() == "This is text file in a directory with superpowers\n"


@pytest.mark.datafiles(os.path.join(DATA_DIR, "multiple-patches"))
def test_stage_multiple_patches(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Track, fetch, build, checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Test the file.txt was patched and changed
    with open(os.path.join(checkoutdir, "file.txt")) as f:
        assert f.read() == "This is text file with more superpowers\n"


@pytest.mark.datafiles(os.path.join(DATA_DIR, "different-strip-level"))
def test_patch_strip_level(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Track, fetch, build, checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Test the file.txt was patched and changed
    with open(os.path.join(checkoutdir, "file.txt")) as f:
        assert f.read() == "This is text file with superpowers\n"
