# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
from shutil import copyfile
import subprocess
import tarfile
import tempfile
import urllib.parse

import pytest

from buildstream import utils
from buildstream.exceptions import ErrorDomain
from buildstream.testing import generate_project, generate_element
from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream.testing._utils.site import HAVE_LZIP
from tests.testutils.file_server import create_file_server
from . import list_dir_contents

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "tar",)


def _assemble_tar(workingdir, srcdir, dstfile):
    old_dir = os.getcwd()
    os.chdir(workingdir)
    with tarfile.open(dstfile, "w:gz") as tar:
        tar.add(srcdir)
    os.chdir(old_dir)


def _assemble_tar_lz(workingdir, srcdir, dstfile):
    old_dir = os.getcwd()
    os.chdir(workingdir)
    with tempfile.TemporaryFile() as uncompressed:
        with tarfile.open(fileobj=uncompressed, mode="w:") as tar:
            tar.add(srcdir)
        uncompressed.seek(0, 0)
        with open(dstfile, "wb") as dst:
            subprocess.call(["lzip"], stdin=uncompressed, stdout=dst)
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
    src_tar = os.path.join(str(tmpdir), "a.tar.gz")
    _assemble_tar(os.path.join(str(datafiles), "content"), "a", src_tar)

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
    src_tar = os.path.join(str(tmpdir), "a.tar.gz")
    _assemble_tar(os.path.join(str(datafiles), "content"), "a", src_tar)

    # Track it
    result = cli.run(project=project, args=["source", "track", "target.bst"])
    result.assert_success()
    assert "Potential man-in-the-middle attack!" in result.stderr


# Test that a staged checkout matches what was tarred up, with the default first subdir
@pytest.mark.datafiles(os.path.join(DATA_DIR, "fetch"))
@pytest.mark.parametrize("srcdir", ["a", "./a"])
def test_stage_default_basedir(cli, tmpdir, datafiles, srcdir):
    project = str(datafiles)
    generate_project(project, config={"aliases": {"tmpdir": "file:///" + str(tmpdir)}})
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create a local tar
    src_tar = os.path.join(str(tmpdir), "a.tar.gz")
    _assemble_tar(os.path.join(str(datafiles), "content"), srcdir, src_tar)

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
@pytest.mark.parametrize("srcdir", ["a", "./a"])
def test_stage_no_basedir(cli, tmpdir, datafiles, srcdir):
    project = str(datafiles)
    generate_project(project, config={"aliases": {"tmpdir": "file:///" + str(tmpdir)}})
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create a local tar
    src_tar = os.path.join(str(tmpdir), "a.tar.gz")
    _assemble_tar(os.path.join(str(datafiles), "content"), srcdir, src_tar)

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
@pytest.mark.parametrize("srcdir", ["a", "./a"])
def test_stage_explicit_basedir(cli, tmpdir, datafiles, srcdir):
    project = str(datafiles)
    generate_project(project, config={"aliases": {"tmpdir": "file:///" + str(tmpdir)}})
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create a local tar
    src_tar = os.path.join(str(tmpdir), "a.tar.gz")
    _assemble_tar(os.path.join(str(datafiles), "content"), srcdir, src_tar)

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


# Test that we succeed to extract tarballs with hardlinks when stripping the
# leading paths
@pytest.mark.datafiles(os.path.join(DATA_DIR, "contains-links"))
def test_stage_contains_links(cli, tmpdir, datafiles):
    project = str(datafiles)
    generate_project(project, config={"aliases": {"tmpdir": "file:///" + str(tmpdir)}})
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create a local tar
    src_tar = os.path.join(str(tmpdir), "a.tar.gz")

    # Create a hardlink, we wont trust git to store that info for us
    os.makedirs(os.path.join(str(datafiles), "content", "base-directory", "subdir2"), exist_ok=True)
    file1 = os.path.join(str(datafiles), "content", "base-directory", "subdir1", "file.txt")
    file2 = os.path.join(str(datafiles), "content", "base-directory", "subdir2", "file.txt")
    os.link(file1, file2)

    _assemble_tar(os.path.join(str(datafiles), "content"), "base-directory", src_tar)

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
    original_dir = os.path.join(str(datafiles), "content", "base-directory")
    original_contents = list_dir_contents(original_dir)
    checkout_contents = list_dir_contents(checkoutdir)
    assert checkout_contents == original_contents


@pytest.mark.skipif(not HAVE_LZIP, reason="lzip is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "fetch"))
@pytest.mark.parametrize("srcdir", ["a", "./a"])
def test_stage_default_basedir_lzip(cli, tmpdir, datafiles, srcdir):
    project = str(datafiles)
    generate_project(project, config={"aliases": {"tmpdir": "file:///" + str(tmpdir)}})
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create a local tar
    src_tar = os.path.join(str(tmpdir), "a.tar.lz")
    _assemble_tar_lz(os.path.join(str(datafiles), "content"), srcdir, src_tar)

    # Track, fetch, build, checkout
    result = cli.run(project=project, args=["source", "track", "target-lz.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["source", "fetch", "target-lz.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["build", "target-lz.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target-lz.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the content of the first directory is checked out (base-dir: '*')
    original_dir = os.path.join(str(datafiles), "content", "a")
    original_contents = list_dir_contents(original_dir)
    checkout_contents = list_dir_contents(checkoutdir)
    assert checkout_contents == original_contents


# Test that tarballs with read-only files work
# a - contains read-only files in a writable directory
# b - root directory has read-only permission
# c - contains one file that has no read nor write permissions. Base-dir set to '' to extract root of tarball
@pytest.mark.datafiles(os.path.join(DATA_DIR, "read-only"))
@pytest.mark.parametrize("tar_name, base_dir", [("a", "*"), ("b", "*"), ("c", "")])
def test_read_only_dir(cli, tmpdir, datafiles, tar_name, base_dir):
    try:
        project = str(datafiles)
        generate_project(project, config={"aliases": {"tmpdir": "file:///" + str(tmpdir)}})

        tar_file = "{}.tar.gz".format(tar_name)

        generate_element(
            project,
            "target.bst",
            {
                "kind": "import",
                "sources": [{"kind": "tar", "url": "tmpdir:/{}".format(tar_file), "ref": "foo", "base-dir": base_dir}],
            },
        )

        # Get the tarball in tests/sources/tar/read-only/content
        #
        # NOTE that we need to do this because tarfile.open and tar.add()
        # are packing the tar up with writeable files and dirs
        tarball = os.path.join(str(datafiles), "content", tar_file)
        if not os.path.exists(tarball):
            raise FileNotFoundError("{} does not exist".format(tarball))
        copyfile(tarball, os.path.join(str(tmpdir), tar_file))

        # Because this test can potentially leave directories behind
        # which are difficult to remove, ask buildstream to use
        # our temp directory, so we can clean up.
        tmpdir_str = str(tmpdir)
        if not tmpdir_str.endswith(os.path.sep):
            tmpdir_str += os.path.sep
        env = {"TMP": tmpdir_str}

        # Track, fetch, build, checkout
        result = cli.run(project=project, args=["source", "track", "target.bst"], env=env)
        result.assert_success()
        result = cli.run(project=project, args=["source", "fetch", "target.bst"], env=env)
        result.assert_success()
        result = cli.run(project=project, args=["build", "target.bst"], env=env)
        result.assert_success()

    finally:
        utils._force_rmtree(str(tmpdir))


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

        src_tar = os.path.join(file_server_files, "a.tar.gz")
        _assemble_tar(os.path.join(str(datafiles), "content"), "a", src_tar)

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


@pytest.mark.parametrize("server_type", ("FTP", "HTTP"))
@pytest.mark.datafiles(os.path.join(DATA_DIR, "fetch"))
def test_netrc_already_specified_user(cli, datafiles, server_type, tmpdir):
    file_server_files = os.path.join(str(tmpdir), "file_server")
    fake_home = os.path.join(str(tmpdir), "fake_home")
    os.makedirs(file_server_files, exist_ok=True)
    os.makedirs(fake_home, exist_ok=True)
    project = str(datafiles)

    os.environ["HOME"] = fake_home
    with open(os.path.join(fake_home, ".netrc"), "wb") as f:
        os.fchmod(f.fileno(), 0o700)
        f.write(b"machine 127.0.0.1\n")
        f.write(b"login testuser\n")
        f.write(b"password 12345\n")

    with create_file_server(server_type) as server:
        server.add_user("otheruser", "12345", file_server_files)
        parts = urllib.parse.urlsplit(server.base_url())
        base_url = urllib.parse.urlunsplit([parts[0], "otheruser@{}".format(parts[1]), *parts[2:]])
        generate_project(project, config={"aliases": {"tmpdir": base_url}})

        src_tar = os.path.join(file_server_files, "a.tar.gz")
        _assemble_tar(os.path.join(str(datafiles), "content"), "a", src_tar)

        server.start()

        result = cli.run(project=project, args=["source", "track", "target.bst"])
        result.assert_main_error(ErrorDomain.STREAM, None)
        result.assert_task_error(ErrorDomain.SOURCE, None)


# Test that BuildStream doesnt crash if HOME is unset while
# the netrc module is trying to find it's ~/.netrc file.
@pytest.mark.datafiles(os.path.join(DATA_DIR, "fetch"))
def test_homeless_environment(cli, tmpdir, datafiles):
    project = str(datafiles)
    generate_project(project, config={"aliases": {"tmpdir": "file:///" + str(tmpdir)}})

    # Create a local tar
    src_tar = os.path.join(str(tmpdir), "a.tar.gz")
    _assemble_tar(os.path.join(str(datafiles), "content"), "a", src_tar)

    # Use a track, make sure the plugin tries to find a ~/.netrc
    result = cli.run(project=project, args=["source", "track", "target.bst"], env={"HOME": None})
    result.assert_success()


@pytest.mark.datafiles(os.path.join(DATA_DIR, "out-of-basedir-hardlinks"))
def test_out_of_basedir_hardlinks(cli, tmpdir, datafiles):
    def ensure_link(member):
        # By default, python will simply duplicate files - we want
        # hardlinks!
        if member.path == "contents/to_extract/a":
            member.type = tarfile.LNKTYPE
            member.linkname = "contents/elsewhere/a"
        return member

    project = str(datafiles)
    generate_project(project, config={"aliases": {"tmpdir": "file:///" + str(tmpdir)}})
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create a tarball with an odd hardlink
    src_tar = os.path.join(str(tmpdir), "contents.tar.gz")
    old_dir = os.getcwd()
    os.chdir(str(tmpdir))
    with tarfile.open(src_tar, "w:gz") as tar:
        # Don't recursively add `contents` as the order is not guaranteed.
        # We need to add `elsewhere` before `to_extract` as the latter
        # references the former in `linkname`.
        tar.add("contents", recursive=False)
        tar.add("contents/elsewhere")
        tar.add("contents/to_extract", filter=ensure_link)
    os.chdir(old_dir)

    # Make sure our tarfile is actually created with the desired
    # attributes set
    with tarfile.open(src_tar, "r:gz") as tar:
        assert any(
            member.islnk() and member.path == "contents/to_extract/a" and member.linkname == "contents/elsewhere/a"
            for member in tar.getmembers()
        )

    # Assert that we will actually create a singular copy of the file
    result = cli.run(project=project, args=["source", "track", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    original_dir = os.path.join(str(datafiles), "contents", "to_extract")
    original_contents = list_dir_contents(original_dir)
    checkout_contents = list_dir_contents(checkoutdir)
    assert checkout_contents == original_contents


@pytest.mark.datafiles(os.path.join(DATA_DIR, "out-of-basedir-hardlinks"))
def test_malicious_out_of_basedir_hardlinks(cli, tmpdir, datafiles):
    project = str(datafiles)
    generate_project(project, config={"aliases": {"tmpdir": "file:///" + str(tmpdir)}})

    # Create a maliciously-hardlinked tarball
    def ensure_link(member):
        # By default, python will simply duplicate files - we want
        # hardlinks!
        if member.path == "contents/elsewhere/malicious":
            member.type = tarfile.LNKTYPE
            # This should not be allowed
            member.linkname = "../../../malicious_target.bst"
        return member

    src_tar = os.path.join(str(tmpdir), "contents.tar.gz")
    old_dir = os.getcwd()
    os.chdir(str(tmpdir))
    with tarfile.open(src_tar, "w:gz") as tar:
        tar.add("contents", filter=ensure_link)
    os.chdir(old_dir)

    # Make sure our tarfile is actually created with the desired
    # attributes set
    with tarfile.open(src_tar, "r:gz") as tar:
        assert any(
            member.islnk()
            and member.path == "contents/elsewhere/malicious"
            and member.linkname == "../../../malicious_target.bst"
            for member in tar.getmembers()
        )

    # Try to execute the exploit
    result = cli.run(project=project, args=["source", "track", "malicious_target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["source", "fetch", "malicious_target.bst"])
    result.assert_main_error(ErrorDomain.STREAM, None)
