import os
import pytest
import tarfile
import tempfile
import subprocess

from buildstream._exceptions import ErrorDomain
from buildstream import _yaml
from tests.testutils import cli
from tests.testutils.site import HAVE_LZIP
from . import list_dir_contents

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'tar',
)


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
        with open(dstfile, 'wb') as dst:
            subprocess.call(['lzip'],
                            stdin=uncompressed,
                            stdout=dst)
    os.chdir(old_dir)


def generate_project(project_dir, tmpdir):
    project_file = os.path.join(project_dir, "project.conf")
    _yaml.dump({
        'name': 'foo',
        'aliases': {
            'tmpdir': "file:///" + str(tmpdir)
        }
    }, project_file)


# Test that without ref, consistency is set appropriately.
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'no-ref'))
def test_no_ref(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)
    assert cli.get_element_state(project, 'target.bst') == 'no reference'


# Test that when I fetch a nonexistent URL, errors are handled gracefully and a retry is performed.
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'fetch'))
def test_fetch_bad_url(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)

    # Try to fetch it
    result = cli.run(project=project, args=[
        'fetch', 'target.bst'
    ])
    assert "FAILURE Try #" in result.stderr
    result.assert_main_error(ErrorDomain.STREAM, None)
    result.assert_task_error(ErrorDomain.SOURCE, None)


# Test that when I fetch with an invalid ref, it fails.
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'fetch'))
def test_fetch_bad_ref(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)

    # Create a local tar
    src_tar = os.path.join(str(tmpdir), "a.tar.gz")
    _assemble_tar(os.path.join(str(datafiles), "content"), "a", src_tar)

    # Try to fetch it
    result = cli.run(project=project, args=[
        'fetch', 'target.bst'
    ])
    result.assert_main_error(ErrorDomain.STREAM, None)
    result.assert_task_error(ErrorDomain.SOURCE, None)


# Test that when tracking with a ref set, there is a warning
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'fetch'))
def test_track_warning(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)

    # Create a local tar
    src_tar = os.path.join(str(tmpdir), "a.tar.gz")
    _assemble_tar(os.path.join(str(datafiles), "content"), "a", src_tar)

    # Track it
    result = cli.run(project=project, args=[
        'track', 'target.bst'
    ])
    result.assert_success()
    assert "Potential man-in-the-middle attack!" in result.stderr


# Test that a staged checkout matches what was tarred up, with the default first subdir
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'fetch'))
@pytest.mark.parametrize("srcdir", ["a", "./a"])
def test_stage_default_basedir(cli, tmpdir, datafiles, srcdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create a local tar
    src_tar = os.path.join(str(tmpdir), "a.tar.gz")
    _assemble_tar(os.path.join(str(datafiles), "content"), srcdir, src_tar)

    # Track, fetch, build, checkout
    result = cli.run(project=project, args=['track', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['fetch', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    result.assert_success()

    # Check that the content of the first directory is checked out (base-dir: '*')
    original_dir = os.path.join(str(datafiles), "content", "a")
    original_contents = list_dir_contents(original_dir)
    checkout_contents = list_dir_contents(checkoutdir)
    assert(checkout_contents == original_contents)


# Test that a staged checkout matches what was tarred up, with an empty base-dir
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'no-basedir'))
@pytest.mark.parametrize("srcdir", ["a", "./a"])
def test_stage_no_basedir(cli, tmpdir, datafiles, srcdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create a local tar
    src_tar = os.path.join(str(tmpdir), "a.tar.gz")
    _assemble_tar(os.path.join(str(datafiles), "content"), srcdir, src_tar)

    # Track, fetch, build, checkout
    result = cli.run(project=project, args=['track', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['fetch', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    result.assert_success()

    # Check that the full content of the tarball is checked out (base-dir: '')
    original_dir = os.path.join(str(datafiles), "content")
    original_contents = list_dir_contents(original_dir)
    checkout_contents = list_dir_contents(checkoutdir)
    assert(checkout_contents == original_contents)


# Test that a staged checkout matches what was tarred up, with an explicit basedir
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'explicit-basedir'))
@pytest.mark.parametrize("srcdir", ["a", "./a"])
def test_stage_explicit_basedir(cli, tmpdir, datafiles, srcdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create a local tar
    src_tar = os.path.join(str(tmpdir), "a.tar.gz")
    _assemble_tar(os.path.join(str(datafiles), "content"), srcdir, src_tar)

    # Track, fetch, build, checkout
    result = cli.run(project=project, args=['track', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['fetch', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    result.assert_success()

    # Check that the content of the first directory is checked out (base-dir: '*')
    original_dir = os.path.join(str(datafiles), "content", "a")
    original_contents = list_dir_contents(original_dir)
    checkout_contents = list_dir_contents(checkoutdir)
    assert(checkout_contents == original_contents)


# Test that we succeed to extract tarballs with hardlinks when stripping the
# leading paths
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'contains-links'))
def test_stage_contains_links(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)
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
    result = cli.run(project=project, args=['track', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['fetch', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    result.assert_success()

    # Check that the content of the first directory is checked out (base-dir: '*')
    original_dir = os.path.join(str(datafiles), "content", "base-directory")
    original_contents = list_dir_contents(original_dir)
    checkout_contents = list_dir_contents(checkoutdir)
    assert(checkout_contents == original_contents)


@pytest.mark.skipif(not HAVE_LZIP, reason='lzip is not available')
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'fetch'))
@pytest.mark.parametrize("srcdir", ["a", "./a"])
def test_stage_default_basedir_lzip(cli, tmpdir, datafiles, srcdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create a local tar
    src_tar = os.path.join(str(tmpdir), "a.tar.lz")
    _assemble_tar_lz(os.path.join(str(datafiles), "content"), srcdir, src_tar)

    # Track, fetch, build, checkout
    result = cli.run(project=project, args=['track', 'target-lz.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['fetch', 'target-lz.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['build', 'target-lz.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target-lz.bst', checkoutdir])
    result.assert_success()

    # Check that the content of the first directory is checked out (base-dir: '*')
    original_dir = os.path.join(str(datafiles), "content", "a")
    original_contents = list_dir_contents(original_dir)
    checkout_contents = list_dir_contents(checkoutdir)
    assert(checkout_contents == original_contents)
