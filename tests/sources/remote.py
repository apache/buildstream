import os
import pytest

from buildstream._exceptions import ErrorDomain
from buildstream import _yaml
from tests.testutils import cli

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'remote',
)


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


# Here we are doing a fetch on a file that doesn't exist. target.bst
# refers to 'file' but that file is not present.
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'missing-file'))
def test_missing_file(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)

    # Try to fetch it
    result = cli.run(project=project, args=[
        'fetch', 'target.bst'
    ])

    result.assert_main_error(ErrorDomain.STREAM, None)
    result.assert_task_error(ErrorDomain.SOURCE, None)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'path-in-filename'))
def test_path_in_filename(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)

    # Try to fetch it
    result = cli.run(project=project, args=[
        'fetch', 'target.bst'
    ])

    # The bst file has a / in the filename param
    result.assert_main_error(ErrorDomain.SOURCE, "filename-contains-directory")


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'single-file'))
def test_simple_file_build(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Try to fetch it
    result = cli.run(project=project, args=[
        'fetch', 'target.bst'
    ])
    result.assert_success()

    result = cli.run(project=project, args=[
        'build', 'target.bst'
    ])
    result.assert_success()

    result = cli.run(project=project, args=[
        'checkout', 'target.bst', checkoutdir
    ])
    result.assert_success()
    # Note that the url of the file in target.bst is actually /dir/file
    # but this tests confirms we take the basename
    assert(os.path.exists(os.path.join(checkoutdir, 'file')))


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'single-file-custom-name'))
def test_simple_file_custom_name_build(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Try to fetch it
    result = cli.run(project=project, args=[
        'fetch', 'target.bst'
    ])
    result.assert_success()

    result = cli.run(project=project, args=[
        'build', 'target.bst'
    ])
    result.assert_success()

    result = cli.run(project=project, args=[
        'checkout', 'target.bst', checkoutdir
    ])
    result.assert_success()
    assert(not os.path.exists(os.path.join(checkoutdir, 'file')))
    assert(os.path.exists(os.path.join(checkoutdir, 'custom-file')))


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'unique-keys'))
def test_unique_key(cli, tmpdir, datafiles):
    '''This test confirms that the 'filename' parameter is honoured when it comes
    to generating a cache key for the source.
    '''
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)
    assert cli.get_element_state(project, 'target.bst') == "fetch needed"
    assert cli.get_element_state(project, 'target-custom.bst') == "fetch needed"
    # Try to fetch it
    result = cli.run(project=project, args=[
        'fetch', 'target.bst'
    ])

    # We should download the file only once
    assert cli.get_element_state(project, 'target.bst') == 'buildable'
    assert cli.get_element_state(project, 'target-custom.bst') == 'buildable'

    # But the cache key is different because the 'filename' is different.
    assert cli.get_element_key(project, 'target.bst') != \
        cli.get_element_key(project, 'target-custom.bst')
