#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest
from buildstream._testing import cli  # pylint: disable=unused-import

from buildstream import _yaml
from buildstream import utils
from buildstream._frontend.app import App
from buildstream.exceptions import ErrorDomain, LoadErrorReason


def get_default_min_version():
    bst_major, bst_minor = utils.get_bst_version()

    # For the version check, artificially set the version to at least
    # version 2.0
    #
    # TODO: Remove this code block after releasing 2.0
    #
    if bst_major < 2:
        bst_major = 2
        bst_minor = 0

    return "{}.{}".format(bst_major, bst_minor)


def test_defaults(cli, tmpdir):
    project = str(tmpdir)
    project_path = os.path.join(project, "project.conf")

    result = cli.run(args=["init", "--project-name", "foo", project])
    result.assert_success()

    project_conf = _yaml.load(project_path, shortname=None)
    assert project_conf.get_str("name") == "foo"
    assert project_conf.get_str("min-version") == get_default_min_version()
    assert project_conf.get_str("element-path") == "elements"


def test_all_options(cli, tmpdir):
    project = str(tmpdir)
    project_path = os.path.join(project, "project.conf")

    result = cli.run(
        args=["init", "--project-name", "foo", "--min-version", "2.0", "--element-path", "ponies", project]
    )
    result.assert_success()

    project_conf = _yaml.load(project_path, shortname=None)
    assert project_conf.get_str("name") == "foo"
    assert project_conf.get_str("min-version") == "2.0"
    assert project_conf.get_str("element-path") == "ponies"

    elements_dir = os.path.join(project, "ponies")
    assert os.path.isdir(elements_dir)


def test_no_project_name(cli, tmpdir):
    result = cli.run(args=["init", str(tmpdir)])
    result.assert_main_error(ErrorDomain.APP, "unspecified-project-name")


def test_project_exists(cli, tmpdir):
    project = str(tmpdir)
    project_path = os.path.join(project, "project.conf")
    with open(project_path, "w", encoding="utf-8") as f:
        f.write("name: pony\n")

    result = cli.run(args=["init", "--project-name", "foo", project])
    result.assert_main_error(ErrorDomain.APP, "project-exists")


def test_force_overwrite_project(cli, tmpdir):
    project = str(tmpdir)
    project_path = os.path.join(project, "project.conf")
    with open(project_path, "w", encoding="utf-8") as f:
        f.write("name: pony\n")

    result = cli.run(args=["init", "--project-name", "foo", "--force", project])
    result.assert_success()

    project_conf = _yaml.load(project_path, shortname=None)
    assert project_conf.get_str("name") == "foo"
    assert project_conf.get_str("min-version") == get_default_min_version()


def test_relative_path_directory_as_argument(cli, tmpdir):
    project = os.path.join(str(tmpdir), "child-directory")
    os.makedirs(project, exist_ok=True)
    project_path = os.path.join(project, "project.conf")
    rel_path = os.path.relpath(project)

    result = cli.run(args=["init", "--project-name", "foo", rel_path])
    result.assert_success()

    project_conf = _yaml.load(project_path, shortname=None)
    assert project_conf.get_str("name") == "foo"
    assert project_conf.get_str("min-version") == get_default_min_version()
    assert project_conf.get_str("element-path") == "elements"


def test_set_directory_and_directory_as_argument(cli, tmpdir):
    result = cli.run(args=["-C", "/foo/bar", "init", "--project-name", "foo", "/boo/far"])
    result.assert_main_error(ErrorDomain.APP, "init-with-set-directory")


@pytest.mark.parametrize("project_name", [("Micheal Jackson"), ("one+one")])
def test_bad_project_name(cli, tmpdir, project_name):
    result = cli.run(args=["init", "--project-name", str(tmpdir)])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_SYMBOL_NAME)


@pytest.mark.parametrize("min_version", [("-1"), ("1.4"), ("2.900"), ("abc")])
def test_bad_min_version(cli, tmpdir, min_version):
    result = cli.run(args=["init", "--project-name", "foo", "--min-version", min_version, str(tmpdir)])
    result.assert_main_error(ErrorDomain.APP, "invalid-min-version")


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

        def _init_project_interactive(self, *args, **kwargs):  # pylint: disable=signature-differs
            return ("project_name", "2.0", element_path)

    monkeypatch.setattr(App, "create", DummyInteractiveApp.create)

    result = cli.run(args=["init", str(project)])
    result.assert_success()

    full_element_path = project.joinpath(element_path)
    assert full_element_path.exists()

    project_conf = _yaml.load(str(project_conf_path), shortname=None)
    assert project_conf.get_str("name") == "project_name"
    assert project_conf.get_str("min-version") == "2.0"
    assert project_conf.get_str("element-path") == element_path
