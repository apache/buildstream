import os
import pytest

from buildstream._exceptions import ErrorDomain
from buildstream import _yaml
from tests.testutils import cli

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'pip',
)


def generate_project(project_dir, tmpdir):
    project_file = os.path.join(project_dir, "project.conf")
    _yaml.dump({'name': 'foo'}, project_file)


# Test that without ref, consistency is set appropriately.
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'no-ref'))
def test_no_ref(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)
    assert cli.get_element_state(project, 'target.bst') == 'no reference'


# Test that pip is not allowed to be the first source
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'first-source-pip'))
def test_first_source(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)
    result = cli.run(project=project, args=[
        'show', 'target.bst'
    ])
    result.assert_main_error(ErrorDomain.ELEMENT, None)


# Test that error is raised when neither packges nor requirements files
# have been specified
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'no-packages'))
def test_no_packages(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project, tmpdir)
    result = cli.run(project=project, args=[
        'show', 'target.bst'
    ])
    result.assert_main_error(ErrorDomain.SOURCE, None)
