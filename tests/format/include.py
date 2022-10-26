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
import textwrap
import pytest
from buildstream import _yaml
from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream._testing import cli  # pylint: disable=unused-import
from buildstream._testing import create_repo
from tests.testutils import generate_junction


# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "include")


@pytest.mark.datafiles(DATA_DIR)
def test_include_project_file(cli, datafiles):
    project = os.path.join(str(datafiles), "file")
    result = cli.run(project=project, args=["show", "--deps", "none", "--format", "%{vars}", "element.bst"])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_bool("included")


def test_include_missing_file(cli, tmpdir):
    tmpdir.join("project.conf").write('{"name": "test", "min-version": "2.0"}')
    element = tmpdir.join("include_missing_file.bst")

    # Normally we would use dicts and _yaml.roundtrip_dump to write such things, but here
    # we want to be sure of a stable line and column number.
    element.write(
        textwrap.dedent(
            """
        kind: manual

        "(@)":
          - nosuch.yaml
    """
        ).strip()
    )

    result = cli.run(project=str(tmpdir), args=["show", str(element.basename)])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)
    # Make sure the root cause provenance is in the output.
    assert "include_missing_file.bst [line 4 column 4]" in result.stderr


def test_include_dir(cli, tmpdir):
    tmpdir.join("project.conf").write('{"name": "test", "min-version": "2.0"}')
    tmpdir.mkdir("subdir")
    element = tmpdir.join("include_dir.bst")

    # Normally we would use dicts and _yaml.roundtrip_dump to write such things, but here
    # we want to be sure of a stable line and column number.
    element.write(
        textwrap.dedent(
            """
        kind: manual

        "(@)":
          - subdir/
    """
        ).strip()
    )

    result = cli.run(project=str(tmpdir), args=["show", str(element.basename)])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.LOADING_DIRECTORY)
    # Make sure the root cause provenance is in the output.
    assert "include_dir.bst [line 4 column 4]" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_include_junction_file(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "junction")

    generate_junction(
        tmpdir, os.path.join(project, "subproject"), os.path.join(project, "junction.bst"), store_ref=True
    )

    result = cli.run(project=project, args=["show", "--deps", "none", "--format", "%{vars}", "element.bst"])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_bool("included")


@pytest.mark.datafiles(DATA_DIR)
def test_include_junction_options(cli, datafiles):
    project = os.path.join(str(datafiles), "options")

    result = cli.run(
        project=project,
        args=["-o", "build_arch", "x86_64", "show", "--deps", "none", "--format", "%{vars}", "element.bst"],
    )
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_str("build_arch") == "x86_64"


@pytest.mark.datafiles(DATA_DIR)
def test_junction_element_partial_project_project(cli, tmpdir, datafiles):
    """
    Junction elements never depend on fully include processed project.
    """

    project = os.path.join(str(datafiles), "junction")

    subproject_path = os.path.join(project, "subproject")
    junction_path = os.path.join(project, "junction.bst")

    repo = create_repo("tar", str(tmpdir))

    ref = repo.create(subproject_path)

    element = {"kind": "junction", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, junction_path)

    result = cli.run(project=project, args=["show", "--deps", "none", "--format", "%{vars}", "junction.bst"])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_str("included", default=None) is None


@pytest.mark.datafiles(DATA_DIR)
def test_junction_element_not_partial_project_file(cli, tmpdir, datafiles):
    """
    Junction elements never depend on fully include processed project.
    """

    project = os.path.join(str(datafiles), "file_with_subproject")

    subproject_path = os.path.join(project, "subproject")
    junction_path = os.path.join(project, "junction.bst")

    repo = create_repo("tar", str(tmpdir))

    ref = repo.create(subproject_path)

    element = {"kind": "junction", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, junction_path)

    result = cli.run(project=project, args=["show", "--deps", "none", "--format", "%{vars}", "junction.bst"])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_str("included", default=None) is not None


@pytest.mark.datafiles(DATA_DIR)
def test_include_element_overrides(cli, datafiles):
    project = os.path.join(str(datafiles), "overrides")

    result = cli.run(project=project, args=["show", "--deps", "none", "--format", "%{vars}", "element.bst"])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_str("manual_main_override", default=None) is not None
    assert loaded.get_str("manual_included_override", default=None) is not None


@pytest.mark.datafiles(DATA_DIR)
def test_include_element_overrides_composition(cli, datafiles):
    project = os.path.join(str(datafiles), "overrides")

    result = cli.run(project=project, args=["show", "--deps", "none", "--format", "%{config}", "element.bst"])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_str_list("build-commands") == ["first", "second"]


@pytest.mark.datafiles(DATA_DIR)
def test_list_overide_does_not_fail_upon_first_composition(cli, datafiles):
    project = os.path.join(str(datafiles), "eventual_overrides")

    result = cli.run(project=project, args=["show", "--deps", "none", "--format", "%{public}", "element.bst"])
    result.assert_success()
    loaded = _yaml.load_data(result.output)

    # Assert that the explicitly overwritten public data is present
    bst = loaded.get_mapping("bst")
    assert "foo-commands" in bst
    assert bst.get_str_list("foo-commands") == ["need", "this"]


@pytest.mark.datafiles(DATA_DIR)
def test_include_element_overrides_sub_include(cli, datafiles):
    project = os.path.join(str(datafiles), "sub-include")

    result = cli.run(project=project, args=["show", "--deps", "none", "--format", "%{vars}", "element.bst"])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_str("included", default=None) is not None


@pytest.mark.datafiles(DATA_DIR)
def test_junction_do_not_use_included_overrides(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "overrides-junction")

    generate_junction(
        tmpdir, os.path.join(project, "subproject"), os.path.join(project, "junction.bst"), store_ref=True
    )

    result = cli.run(project=project, args=["show", "--deps", "none", "--format", "%{vars}", "junction.bst"])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_str("main_override", default=None) is not None
    assert loaded.get_str("included_override", default=None) is None


@pytest.mark.datafiles(DATA_DIR)
def test_conditional_in_fragment(cli, datafiles):
    project = os.path.join(str(datafiles), "conditional")

    result = cli.run(
        project=project,
        args=["-o", "build_arch", "x86_64", "show", "--deps", "none", "--format", "%{vars}", "element.bst"],
    )
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_str("size") == "8"


@pytest.mark.parametrize(
    "project_dir",
    [
        "conditional-conflicts-project",
        "conditional-conflicts-element",
        "conditional-conflicts-options-included",
        "conditional-conflicts-complex",
        "conditional-conflicts-toplevel-precedence",
    ],
)
@pytest.mark.datafiles(DATA_DIR)
def test_preserve_conditionals(cli, datafiles, project_dir):
    project = os.path.join(str(datafiles), project_dir)

    result = cli.run(
        project=project,
        args=["-o", "build_arch", "i586", "show", "--deps", "none", "--format", "%{vars}", "element.bst"],
    )
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_str("enable-work-around") == "true"
    assert loaded.get_str("size") == "4"


@pytest.mark.datafiles(DATA_DIR)
def test_inner(cli, datafiles):
    project = os.path.join(str(datafiles), "inner")
    result = cli.run(
        project=project,
        args=["-o", "build_arch", "x86_64", "show", "--deps", "none", "--format", "%{vars}", "element.bst"],
    )
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_str("build_arch") == "x86_64"


@pytest.mark.datafiles(DATA_DIR)
def test_recursive_include(cli, datafiles):
    project = os.path.join(str(datafiles), "recursive")

    result = cli.run(project=project, args=["show", "--deps", "none", "--format", "%{vars}", "element.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.RECURSIVE_INCLUDE)
    assert "line 2 column 2" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_local_to_junction(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "local_to_junction")

    generate_junction(
        tmpdir, os.path.join(project, "subproject"), os.path.join(project, "junction.bst"), store_ref=True
    )

    result = cli.run(project=project, args=["show", "--deps", "none", "--format", "%{vars}", "element.bst"])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_bool("included")


@pytest.mark.datafiles(DATA_DIR)
def test_option_from_junction(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "junction_options")

    generate_junction(
        tmpdir,
        os.path.join(project, "subproject"),
        os.path.join(project, "junction.bst"),
        store_ref=True,
        options={"local_option": "set"},
    )

    result = cli.run(project=project, args=["show", "--deps", "none", "--format", "%{vars}", "element.bst"])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert not loaded.get_bool("is-default")


@pytest.mark.datafiles(DATA_DIR)
def test_option_from_junction_element(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "junction_options_element")

    generate_junction(
        tmpdir,
        os.path.join(project, "subproject"),
        os.path.join(project, "junction.bst"),
        store_ref=True,
        options={"local_option": "set"},
    )

    result = cli.run(project=project, args=["show", "--deps", "none", "--format", "%{vars}", "element.bst"])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert not loaded.get_bool("is-default")


@pytest.mark.datafiles(DATA_DIR)
def test_option_from_deep_junction(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "junction_options_deep")
    junction_repo_a = os.path.join(tmpdir, "a")
    junction_repo_b = os.path.join(tmpdir, "b")

    generate_junction(
        junction_repo_a,
        os.path.join(project, "subproject-2"),
        os.path.join(project, "subproject-1", "junction-2.bst"),
        store_ref=True,
        options={"local_option": "set"},
    )

    generate_junction(
        junction_repo_b,
        os.path.join(project, "subproject-1"),
        os.path.join(project, "junction-1.bst"),
        store_ref=True,
    )

    result = cli.run(project=project, args=["show", "--deps", "none", "--format", "%{vars}", "element.bst"])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert not loaded.get_bool("is-default")


@pytest.mark.datafiles(DATA_DIR)
def test_include_full_path(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "full_path")

    result = cli.run(project=project, args=["show", "--deps", "none", "--format", "%{vars}", "element.bst"])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_str("bar") == "red"
    assert loaded.get_str("foo") == "blue"


@pytest.mark.datafiles(DATA_DIR)
def test_include_invalid_full_path(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "full_path")

    result = cli.run(project=project, args=["show", "--deps", "none", "--format", "%{vars}", "invalid.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)
    # Make sure the root cause provenance is in the output.
    assert "invalid.bst [line 4 column 7]" in result.stderr
