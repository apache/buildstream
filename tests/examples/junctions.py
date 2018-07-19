import os
import pytest

from tests.testutils import cli_integration as cli
from tests.testutils.integration import assert_contains
from tests.testutils.site import IS_LINUX

pytestmark = pytest.mark.integration

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), '..', '..', 'doc', 'examples', 'junctions'
)

JUNCTION_IMPORT_PATH = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), '..', '..', 'doc', 'examples', 'autotools'
)


def ammend_juntion_path_paths(tmpdir):
    # The junction element in the examples/junctions project uses a local source type.
    # It's "path:" must specify a relative path from the project's root directory.
    # For the hello-junction element to function during these tests, the copy of the junctions
    # project made in the buildstream/tmp/directory, "path:" must be ammended to be the relative
    # path to the autotools example from the temporary test directory.
    junction_element = os.path.join(tmpdir, "elements", "hello-junction.bst")
    junction_element_bst = ""
    junction_relative_path = os.path.relpath(JUNCTION_IMPORT_PATH, tmpdir)
    with open(junction_element, 'r') as f:
        junction_element_bst = f.read()
    ammended_element_bst = junction_element_bst.replace("../autotools", junction_relative_path)
    with open(junction_element, 'w') as f:
        f.write(ammended_element_bst)


# Check that the autotools project is where the junctions example expects and
# contains the hello.bst element.
@pytest.mark.datafiles(DATA_DIR)
def test_autotools_example_is_present(datafiles):
    autotools_path = JUNCTION_IMPORT_PATH
    assert os.path.exists(autotools_path)
    assert os.path.exists(os.path.join(autotools_path, "elements", "hello.bst"))


# Test that the project builds successfully
@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_build(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    ammend_juntion_path_paths(str(tmpdir))

    result = cli.run(project=project, args=['build', 'callHello.bst'])
    result.assert_success()


# Test the callHello script works as expected.
@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_shell_call_hello(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    ammend_juntion_path_paths(str(tmpdir))

    result = cli.run(project=project, args=['build', 'callHello.bst'])
    result.assert_success()

    result = cli.run(project=project, args=['shell', 'callHello.bst', '--', '/bin/sh', 'callHello.sh'])
    result.assert_success()
    assert result.output == 'Calling hello:\nHello World!\nThis is amhello 1.0.\n'


# Test opening a cross-junction workspace
@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_open_cross_junction_workspace(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    workspace_dir = os.path.join(str(tmpdir), "workspace_hello_junction")
    ammend_juntion_path_paths(str(tmpdir))

    result = cli.run(project=project,
                     args=['workspace', 'open', 'hello-junction.bst:hello.bst', workspace_dir])
    result.assert_success()

    result = cli.run(project=project,
                     args=['workspace', 'close', '--remove-dir', 'hello-junction.bst:hello.bst'])
    result.assert_success()
