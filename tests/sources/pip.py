import os
import pytest

from buildstream._exceptions import ErrorDomain
from buildstream import _yaml
from buildstream.plugins.sources.pip import _match_package_name
from buildstream.plugintestutils import cli

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'pip',
)


def generate_project(project_dir):
    project_file = os.path.join(project_dir, "project.conf")
    _yaml.dump({'name': 'foo'}, project_file)


# Test that without ref, consistency is set appropriately.
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'no-ref'))
def test_no_ref(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project)
    assert cli.get_element_state(project, 'target.bst') == 'no reference'


# Test that pip is not allowed to be the first source
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'first-source-pip'))
def test_first_source(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project)
    result = cli.run(project=project, args=[
        'show', 'target.bst'
    ])
    result.assert_main_error(ErrorDomain.ELEMENT, None)


# Test that error is raised when neither packges nor requirements files
# have been specified
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'no-packages'))
def test_no_packages(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    generate_project(project)
    result = cli.run(project=project, args=[
        'show', 'target.bst'
    ])
    result.assert_main_error(ErrorDomain.SOURCE, None)


# Test that pip source parses tar ball names correctly for the ref
@pytest.mark.parametrize(
    'tarball, expected_name, expected_version',
    [
        ('dotted.package-0.9.8.tar.gz', 'dotted.package', '0.9.8'),
        ('hyphenated-package-2.6.0.tar.gz', 'hyphenated-package', '2.6.0'),
        ('underscore_pkg-3.1.0.tar.gz', 'underscore_pkg', '3.1.0'),
        ('numbers2and5-1.0.1.tar.gz', 'numbers2and5', '1.0.1'),
        ('multiple.dots.package-5.6.7.tar.gz', 'multiple.dots.package', '5.6.7'),
        ('multiple-hyphens-package-1.2.3.tar.gz', 'multiple-hyphens-package', '1.2.3'),
        ('multiple_underscore_pkg-3.4.5.tar.gz', 'multiple_underscore_pkg', '3.4.5'),
        ('shortversion-1.0.tar.gz', 'shortversion', '1.0'),
        ('longversion-1.2.3.4.tar.gz', 'longversion', '1.2.3.4')
    ])
def test_match_package_name(tarball, expected_name, expected_version):
    name, version = _match_package_name(tarball)
    assert (expected_name, expected_version) == (name, version)
