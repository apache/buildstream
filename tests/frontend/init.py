# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest
from buildstream.testing import cli  # pylint: disable=unused-import

from buildstream import _yaml
from buildstream._frontend.app import App
from buildstream._exceptions import ErrorDomain, LoadErrorReason
from buildstream._versions import BST_FORMAT_VERSION


def test_defaults(cli, tmpdir):
    project = str(tmpdir)
    project_path = os.path.join(project, 'project.conf')

    result = cli.run(project=project, args=['init', '--project-name', 'foo'])
    result.assert_success()

    project_conf = _yaml.load(project_path)
    assert _yaml.node_get(project_conf, str, 'name') == 'foo'
    assert _yaml.node_get(project_conf, str, 'format-version') == str(BST_FORMAT_VERSION)
    assert _yaml.node_get(project_conf, str, 'element-path') == 'elements'


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
    assert _yaml.node_get(project_conf, str, 'name') == 'foo'
    assert _yaml.node_get(project_conf, str, 'format-version') == str(2)
    assert _yaml.node_get(project_conf, str, 'element-path') == 'ponies'

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
    assert _yaml.node_get(project_conf, str, 'name') == 'foo'
    assert _yaml.node_get(project_conf, str, 'format-version') == str(BST_FORMAT_VERSION)


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


@pytest.mark.parametrize("element_path", [('foo'), ('foo/bar')])
def test_element_path_interactive(cli, tmp_path, monkeypatch, element_path):
    project = tmp_path
    project_conf_path = project.joinpath('project.conf')

    class DummyInteractiveApp(App):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.interactive = True

        @classmethod
        def create(cls, *args, **kwargs):
            return DummyInteractiveApp(*args, **kwargs)

        def _init_project_interactive(self, *args, **kwargs):  # pylint: disable=arguments-differ
            return ('project_name', '0', element_path)

    monkeypatch.setattr(App, 'create', DummyInteractiveApp.create)

    result = cli.run(project=str(project), args=['init'])
    result.assert_success()

    full_element_path = project.joinpath(element_path)
    assert full_element_path.exists()

    project_conf = _yaml.load(str(project_conf_path))
    assert _yaml.node_get(project_conf, str, 'name') == 'project_name'
    assert _yaml.node_get(project_conf, str, 'format-version') == '0'
    assert _yaml.node_get(project_conf, str, 'element-path') == element_path
