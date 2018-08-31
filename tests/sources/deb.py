import os
import pytest
import tarfile
import tempfile
import subprocess
import shutil

from buildstream._exceptions import ErrorDomain
from buildstream import _yaml
from tempfile import TemporaryFile
from tests.testutils import cli
from tests.testutils.site import HAVE_ARPY
from . import list_dir_contents

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'deb',
)

deb_name = "a_deb.deb"


def generate_project(project_dir, tmpdir):
    project_file = os.path.join(project_dir, "project.conf")
    _yaml.dump({
        'name': 'foo',
        'aliases': {
            'tmpdir': "file:///" + str(tmpdir)
        }
    }, project_file)


def _copy_deb(start_location, tmpdir):
    source = os.path.join(start_location, deb_name)
    destination = os.path.join(str(tmpdir), deb_name)
    shutil.copyfile(source, destination)


# Test that without ref, consistency is set appropriately.
@pytest.mark.skipif(HAVE_ARPY is False, reason="arpy is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'no-ref'))
def test_no_ref(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)
    assert cli.get_element_state(project, 'target.bst') == 'no reference'


# Test that when I fetch a nonexistent URL, errors are handled gracefully and a retry is performed.
@pytest.mark.skipif(HAVE_ARPY is False, reason="arpy is not available")
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


@pytest.mark.skipif(HAVE_ARPY is False, reason="arpy is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'fetch'))
def test_fetch_bad_ref(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)

    # Copy test deb to tmpdir
    _copy_deb(DATA_DIR, tmpdir)

    # Try to fetch it
    result = cli.run(project=project, args=[
        'fetch', 'target.bst'
    ])
    result.assert_main_error(ErrorDomain.STREAM, None)
    result.assert_task_error(ErrorDomain.SOURCE, None)


# Test that when tracking with a ref set, there is a warning
@pytest.mark.skipif(HAVE_ARPY is False, reason="arpy is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'fetch'))
def test_track_warning(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)

    # Copy test deb to tmpdir
    _copy_deb(DATA_DIR, tmpdir)

    # Track it
    result = cli.run(project=project, args=[
        'track', 'target.bst'
    ])
    result.assert_success()
    assert "Potential man-in-the-middle attack!" in result.stderr


# Test that a staged checkout matches what was tarred up, with the default first subdir
@pytest.mark.skipif(HAVE_ARPY is False, reason="arpy is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'fetch'))
def test_stage_default_basedir(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Copy test deb to tmpdir
    _copy_deb(DATA_DIR, tmpdir)

    # Track, fetch, build, checkout
    result = cli.run(project=project, args=['track', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['fetch', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    result.assert_success()

    # Check that the content of the first directory is checked out (base-dir: '')
    original_dir = os.path.join(str(datafiles), "content")
    original_contents = list_dir_contents(original_dir)
    checkout_contents = list_dir_contents(checkoutdir)
    assert(checkout_contents == original_contents)


# Test that a staged checkout matches what was tarred up, with an empty base-dir
@pytest.mark.skipif(HAVE_ARPY is False, reason="arpy is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'no-basedir'))
def test_stage_no_basedir(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Copy test deb to tmpdir
    _copy_deb(DATA_DIR, tmpdir)

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
@pytest.mark.skipif(HAVE_ARPY is False, reason="arpy is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'explicit-basedir'))
def test_stage_explicit_basedir(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Copy test deb to tmpdir
    _copy_deb(DATA_DIR, tmpdir)

    # Track, fetch, build, checkout
    result = cli.run(project=project, args=['track', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['fetch', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    result.assert_success()

    # Check that the content of the first directory is checked out (base-dir: '')
    original_dir = os.path.join(str(datafiles), "content")
    original_contents = list_dir_contents(original_dir)
    checkout_contents = list_dir_contents(checkoutdir)
    assert(checkout_contents == original_contents)
