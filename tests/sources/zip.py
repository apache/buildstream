# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import zipfile

import pytest

from buildstream.exceptions import ErrorDomain
from buildstream.testing import generate_project
from buildstream.testing import cli  # pylint: disable=unused-import
from tests.testutils.file_server import create_file_server
from . import list_dir_contents

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "zip",)


def _assemble_zip(workingdir, dstfile):
    old_dir = os.getcwd()
    os.chdir(workingdir)
    with zipfile.ZipFile(dstfile, "w") as zipfp:
        for root, dirs, files in os.walk("."):
            names = dirs + files
            names = [os.path.join(root, name) for name in names]
            for name in names:
                zipfp.write(name)
    os.chdir(old_dir)


# Test that without ref, consistency is set appropriately.
@pytest.mark.datafiles(os.path.join(DATA_DIR, "no-ref"))
def test_no_ref(cli, tmpdir, datafiles):
    project = str(datafiles)
    generate_project(project, config={"aliases": {"tmpdir": "file:///" + str(tmpdir)}})
    assert cli.get_element_state(project, "target.bst") == "no reference"


# Test that when I fetch a nonexistent URL, errors are handled gracefully and a retry is performed.
@pytest.mark.datafiles(os.path.join(DATA_DIR, "fetch"))
def test_fetch_bad_url(cli, tmpdir, datafiles):
    project = str(datafiles)
    generate_project(project, config={"aliases": {"tmpdir": "file:///" + str(tmpdir)}})

    # Try to fetch it
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    assert "FAILURE Try #" in result.stderr
    result.assert_main_error(ErrorDomain.STREAM, None)
    result.assert_task_error(ErrorDomain.SOURCE, None)


# Test that when I fetch with an invalid ref, it fails.
@pytest.mark.datafiles(os.path.join(DATA_DIR, "fetch"))
def test_fetch_bad_ref(cli, tmpdir, datafiles):
    project = str(datafiles)
    generate_project(project, config={"aliases": {"tmpdir": "file:///" + str(tmpdir)}})

    # Create a local tar
    src_zip = os.path.join(str(tmpdir), "a.zip")
    _assemble_zip(os.path.join(str(datafiles), "content"), src_zip)

    # Try to fetch it
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_main_error(ErrorDomain.STREAM, None)
    result.assert_task_error(ErrorDomain.SOURCE, None)


# Test that when tracking with a ref set, there is a warning
@pytest.mark.datafiles(os.path.join(DATA_DIR, "fetch"))
def test_track_warning(cli, tmpdir, datafiles):
    project = str(datafiles)
    generate_project(project, config={"aliases": {"tmpdir": "file:///" + str(tmpdir)}})

    # Create a local tar
    src_zip = os.path.join(str(tmpdir), "a.zip")
    _assemble_zip(os.path.join(str(datafiles), "content"), src_zip)

    # Track it
    result = cli.run(project=project, args=["source", "track", "target.bst"])
    result.assert_success()
    assert "Potential man-in-the-middle attack!" in result.stderr


# Test that a staged checkout matches what was tarred up, with the default first subdir
@pytest.mark.datafiles(os.path.join(DATA_DIR, "fetch"))
def test_stage_default_basedir(cli, tmpdir, datafiles):
    project = str(datafiles)
    generate_project(project, config={"aliases": {"tmpdir": "file:///" + str(tmpdir)}})
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create a local tar
    src_zip = os.path.join(str(tmpdir), "a.zip")
    _assemble_zip(os.path.join(str(datafiles), "content"), src_zip)

    # Track, fetch, build, checkout
    result = cli.run(project=project, args=["source", "track", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the content of the first directory is checked out (base-dir: '*')
    original_dir = os.path.join(str(datafiles), "content", "a")
    original_contents = list_dir_contents(original_dir)
    checkout_contents = list_dir_contents(checkoutdir)
    assert checkout_contents == original_contents


# Test that a staged checkout matches what was tarred up, with an empty base-dir
@pytest.mark.datafiles(os.path.join(DATA_DIR, "no-basedir"))
def test_stage_no_basedir(cli, tmpdir, datafiles):
    project = str(datafiles)
    generate_project(project, config={"aliases": {"tmpdir": "file:///" + str(tmpdir)}})
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create a local tar
    src_zip = os.path.join(str(tmpdir), "a.zip")
    _assemble_zip(os.path.join(str(datafiles), "content"), src_zip)

    # Track, fetch, build, checkout
    result = cli.run(project=project, args=["source", "track", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the full content of the tarball is checked out (base-dir: '')
    original_dir = os.path.join(str(datafiles), "content")
    original_contents = list_dir_contents(original_dir)
    checkout_contents = list_dir_contents(checkoutdir)
    assert checkout_contents == original_contents


# Test that a staged checkout matches what was tarred up, with an explicit basedir
@pytest.mark.datafiles(os.path.join(DATA_DIR, "explicit-basedir"))
def test_stage_explicit_basedir(cli, tmpdir, datafiles):
    project = str(datafiles)
    generate_project(project, config={"aliases": {"tmpdir": "file:///" + str(tmpdir)}})
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create a local tar
    src_zip = os.path.join(str(tmpdir), "a.zip")
    _assemble_zip(os.path.join(str(datafiles), "content"), src_zip)

    # Track, fetch, build, checkout
    result = cli.run(project=project, args=["source", "track", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the content of the first directory is checked out (base-dir: '*')
    original_dir = os.path.join(str(datafiles), "content", "a")
    original_contents = list_dir_contents(original_dir)
    checkout_contents = list_dir_contents(checkoutdir)
    assert checkout_contents == original_contents


@pytest.mark.parametrize("server_type", ("FTP", "HTTP"))
@pytest.mark.datafiles(os.path.join(DATA_DIR, "fetch"))
def test_use_netrc(cli, datafiles, server_type, tmpdir):
    file_server_files = os.path.join(str(tmpdir), "file_server")
    fake_home = os.path.join(str(tmpdir), "fake_home")
    os.makedirs(file_server_files, exist_ok=True)
    os.makedirs(fake_home, exist_ok=True)
    project = str(datafiles)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    os.environ["HOME"] = fake_home
    with open(os.path.join(fake_home, ".netrc"), "wb") as f:
        os.fchmod(f.fileno(), 0o700)
        f.write(b"machine 127.0.0.1\n")
        f.write(b"login testuser\n")
        f.write(b"password 12345\n")

    with create_file_server(server_type) as server:
        server.add_user("testuser", "12345", file_server_files)
        generate_project(project, config={"aliases": {"tmpdir": server.base_url()}})

        src_zip = os.path.join(file_server_files, "a.zip")
        _assemble_zip(os.path.join(str(datafiles), "content"), src_zip)

        server.start()

        result = cli.run(project=project, args=["source", "track", "target.bst"])
        result.assert_success()
        result = cli.run(project=project, args=["source", "fetch", "target.bst"])
        result.assert_success()
        result = cli.run(project=project, args=["build", "target.bst"])
        result.assert_success()
        result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
        result.assert_success()

        original_dir = os.path.join(str(datafiles), "content", "a")
        original_contents = list_dir_contents(original_dir)
        checkout_contents = list_dir_contents(checkoutdir)
        assert checkout_contents == original_contents
