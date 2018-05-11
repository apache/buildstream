import os
import pytest
from tests.testutils import cli

from buildstream import _yaml
from buildstream._exceptions import ErrorDomain, LoadErrorReason
from buildstream._versions import BST_FORMAT_VERSION


def test_defaults(cli, tmpdir):
    project = str(tmpdir)
    project_path = os.path.join(project, 'project.conf')

    result = cli.run(project=project, args=['init', '--project-name', 'foo'])
    result.assert_success()

    project_conf = _yaml.load(project_path)
    assert project_conf['name'] == 'foo'
    assert project_conf['format-version'] == str(BST_FORMAT_VERSION)
    assert project_conf['element-path'] == 'elements'


def test_all_options(cli, tmpdir):
    project = str(tmpdir)
    project_path = os.path.join(project, 'project.conf')

    result = cli.run(project=project, args=[
        'init',
        '--project-name', 'foo',
        '--format-version', '2',
        '--element-path', 'ponies',
    ])
    result.assert_success()

    project_conf = _yaml.load(project_path)
    assert project_conf['name'] == 'foo'
    assert project_conf['format-version'] == str(2)
    assert project_conf['element-path'] == 'ponies'

    elements_dir = os.path.join(project, 'ponies')
    assert os.path.isdir(elements_dir)


def test_no_project_name(cli, tmpdir):
    result = cli.run(project=str(tmpdir), args=['init'])
    result.assert_main_error(ErrorDomain.APP, 'unspecified-project-name')


def test_project_exists(cli, tmpdir):
    project = str(tmpdir)
    project_path = os.path.join(project, 'project.conf')
    with open(project_path, 'w') as f:
        f.write('name: pony\n')

    result = cli.run(project=project, args=['init', '--project-name', 'foo'])
    result.assert_main_error(ErrorDomain.APP, 'project-exists')


def test_force_overwrite_project(cli, tmpdir):
    project = str(tmpdir)
    project_path = os.path.join(project, 'project.conf')
    with open(project_path, 'w') as f:
        f.write('name: pony\n')

    result = cli.run(project=project, args=['init', '--project-name', 'foo', '--force'])
    result.assert_success()

    project_conf = _yaml.load(project_path)
    assert project_conf['name'] == 'foo'
    assert project_conf['format-version'] == str(BST_FORMAT_VERSION)


@pytest.mark.parametrize("project_name", [('Micheal Jackson'), ('one+one')])
def test_bad_project_name(cli, tmpdir, project_name):
    result = cli.run(project=str(tmpdir), args=['init', '--project-name', project_name])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_SYMBOL_NAME)


@pytest.mark.parametrize("format_version", [(str(-1)), (str(BST_FORMAT_VERSION + 1))])
def test_bad_format_version(cli, tmpdir, format_version):
    result = cli.run(project=str(tmpdir), args=[
        'init', '--project-name', 'foo', '--format-version', format_version
    ])
    result.assert_main_error(ErrorDomain.APP, 'invalid-format-version')


@pytest.mark.parametrize("element_path", [('/absolute/path'), ('../outside/of/project')])
def test_bad_element_path(cli, tmpdir, element_path):
    result = cli.run(project=str(tmpdir), args=[
        'init', '--project-name', 'foo', '--element-path', element_path
    ])
    result.assert_main_error(ErrorDomain.APP, 'invalid-element-path')


@pytest.mark.parametrize("element_path", [('/absolute/path'), ('../outside/of/project')])
def test_bad_element_path(cli, tmpdir, element_path):
    result = cli.run(project=str(tmpdir), args=[
        'init', '--project-name', 'foo', '--element-path', element_path
    ])
    result.assert_main_error(ErrorDomain.APP, 'invalid-element-path')
