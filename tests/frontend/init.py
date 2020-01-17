# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest
from buildstream.testing import cli  # pylint: disable=unused-import

from buildstream import _yaml
from buildstream._frontend.app import App
from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream._versions import BST_FORMAT_VERSION


def test_defaults(cli, tmpdir):
    project = str(tmpdir)
    project_path = os.path.join(project, "project.conf")

    result = cli.run(args=["init", "--project-name", "foo", project])
    result.assert_success()

    project_conf = _yaml.load(project_path)
    assert project_conf.get_str("name") == "foo"
    assert project_conf.get_str("format-version") == str(BST_FORMAT_VERSION)
    assert project_conf.get_str("element-path") == "elements"


def test_all_options(cli, tmpdir):
    project = str(tmpdir)
    project_path = os.path.join(project, "project.conf")

    result = cli.run(
        args=["init", "--project-name", "foo", "--format-version", "2", "--element-path", "ponies", project]
    )
    result.assert_success()

    project_conf = _yaml.load(project_path)
    assert project_conf.get_str("name") == "foo"
    assert project_conf.get_str("format-version") == str(2)
    assert project_conf.get_str("element-path") == "ponies"

    elements_dir = os.path.join(project, "ponies")
    assert os.path.isdir(elements_dir)


def test_no_project_name(cli, tmpdir):
    result = cli.run(args=["init", str(tmpdir)])
    result.assert_main_error(ErrorDomain.APP, "unspecified-project-name")


def test_project_exists(cli, tmpdir):
    project = str(tmpdir)
    project_path = os.path.join(project, "project.conf")
    with open(project_path, "w") as f:
        f.write("name: pony\n")

    result = cli.run(args=["init", "--project-name", "foo", project])
    result.assert_main_error(ErrorDomain.APP, "project-exists")


def test_force_overwrite_project(cli, tmpdir):
    project = str(tmpdir)
    project_path = os.path.join(project, "project.conf")
    with open(project_path, "w") as f:
        f.write("name: pony\n")

    result = cli.run(args=["init", "--project-name", "foo", "--force", project])
    result.assert_success()

    project_conf = _yaml.load(project_path)
    assert project_conf.get_str("name") == "foo"
    assert project_conf.get_str("format-version") == str(BST_FORMAT_VERSION)


def test_relative_path_directory_as_argument(cli, tmpdir):
    project = os.path.join(str(tmpdir), "child-directory")
    os.makedirs(project, exist_ok=True)
    project_path = os.path.join(project, "project.conf")
    rel_path = os.path.relpath(project)

    result = cli.run(args=["init", "--project-name", "foo", rel_path])
    result.assert_success()

    project_conf = _yaml.load(project_path)
    assert project_conf.get_str("name") == "foo"
    assert project_conf.get_int("format-version") == BST_FORMAT_VERSION
    assert project_conf.get_str("element-path") == "elements"


def test_set_directory_and_directory_as_argument(cli, tmpdir):
    result = cli.run(args=["-C", "/foo/bar", "init", "--project-name", "foo", "/boo/far"])
    result.assert_main_error(ErrorDomain.APP, "init-with-set-directory")


@pytest.mark.parametrize("project_name", [("Micheal Jackson"), ("one+one")])
def test_bad_project_name(cli, tmpdir, project_name):
    result = cli.run(args=["init", "--project-name", str(tmpdir)])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_SYMBOL_NAME)


@pytest.mark.parametrize("format_version", [(str(-1)), (str(BST_FORMAT_VERSION + 1))])
def test_bad_format_version(cli, tmpdir, format_version):
    result = cli.run(args=["init", "--project-name", "foo", "--format-version", format_version, str(tmpdir)])
    result.assert_main_error(ErrorDomain.APP, "invalid-format-version")


@pytest.mark.parametrize("element_path", [("/absolute/path"), ("../outside/of/project")])
def test_bad_element_path(cli, tmpdir, element_path):
    result = cli.run(args=["init", "--project-name", "foo", "--element-path", element_path, str(tmpdir)])
    result.assert_main_error(ErrorDomain.APP, "invalid-element-path")


@pytest.mark.parametrize("element_path", [("foo"), ("foo/bar")])
def test_element_path_interactive(cli, tmp_path, monkeypatch, element_path):
    project = tmp_path
    project_conf_path = project.joinpath("project.conf")

    class DummyInteractiveApp(App):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.interactive = True

        @classmethod
        def create(cls, *args, **kwargs):
            return DummyInteractiveApp(*args, **kwargs)

        def _init_project_interactive(self, *args, **kwargs):  # pylint: disable=arguments-differ
            return ("project_name", "0", element_path)

    monkeypatch.setattr(App, "create", DummyInteractiveApp.create)

    result = cli.run(args=["init", str(project)])
    result.assert_success()

    full_element_path = project.joinpath(element_path)
    assert full_element_path.exists()

    project_conf = _yaml.load(str(project_conf_path))
    assert project_conf.get_str("name") == "project_name"
    assert project_conf.get_str("format-version") == "0"
    assert project_conf.get_str("element-path") == element_path
