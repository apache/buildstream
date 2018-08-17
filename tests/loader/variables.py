import os
import pytest

from buildstream import _yaml
from buildstream._exceptions import ErrorDomain, LoadErrorReason
from tests.testutils import cli

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'variables',
)

PROTECTED_VARIABLES = [('project-name'), ('element-name'), ('max-jobs')]


@pytest.mark.parametrize('protected_var', PROTECTED_VARIABLES)
@pytest.mark.datafiles(DATA_DIR)
def test_use_of_protected_var_project_conf(cli, tmpdir, datafiles, protected_var):
    project = os.path.join(str(datafiles), 'simple')

    conf = {
        'name': 'test',
        'variables': {
            protected_var: 'some-value'
        }
    }
    _yaml.dump(conf, os.path.join(project, 'project.conf'))

    element = {
        'kind': 'import',
        'sources': [
            {
                'kind': 'local',
                'path': 'foo.txt'
            }
        ],
    }
    _yaml.dump(element, os.path.join(project, 'target.bst'))

    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_main_error(ErrorDomain.LOAD,
                             LoadErrorReason.PROTECTED_VARIABLE_REDEFINED)


@pytest.mark.parametrize('protected_var', PROTECTED_VARIABLES)
@pytest.mark.datafiles(DATA_DIR)
def test_use_of_protected_var_element_overrides(cli, tmpdir, datafiles, protected_var):
    project = os.path.join(str(datafiles), 'simple')

    conf = {
        'name': 'test',
        'elements': {
            'manual': {
                'variables': {
                    protected_var: 'some-value'
                }
            }
        }
    }
    _yaml.dump(conf, os.path.join(project, 'project.conf'))

    element = {
        'kind': 'manual',
        'sources': [
            {
                'kind': 'local',
                'path': 'foo.txt'
            }
        ],
    }
    _yaml.dump(element, os.path.join(project, 'target.bst'))

    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_main_error(ErrorDomain.LOAD,
                             LoadErrorReason.PROTECTED_VARIABLE_REDEFINED)


@pytest.mark.parametrize('protected_var', PROTECTED_VARIABLES)
@pytest.mark.datafiles(DATA_DIR)
def test_use_of_protected_var_in_element(cli, tmpdir, datafiles, protected_var):
    project = os.path.join(str(datafiles), 'simple')

    element = {
        'kind': 'import',
        'sources': [
            {
                'kind': 'local',
                'path': 'foo.txt'
            }
        ],
        'variables': {
            protected_var: 'some-value'
        }
    }
    _yaml.dump(element, os.path.join(project, 'target.bst'))

    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_main_error(ErrorDomain.LOAD,
                             LoadErrorReason.PROTECTED_VARIABLE_REDEFINED)
