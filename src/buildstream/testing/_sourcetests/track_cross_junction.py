#
#  Copyright (C) 2018 Codethink Limited
#  Copyright (C) 2019 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os

import pytest

from buildstream import _yaml
from .._utils import generate_junction
from .. import create_repo, ALL_REPO_KINDS
from .. import cli  # pylint: disable=unused-import
from .utils import add_plugins_conf


# Project directory
TOP_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TOP_DIR, "project")


def generate_element(repo, element_path, dep_name=None):
    element = {"kind": "import", "sources": [repo.source_config()]}
    if dep_name:
        element["depends"] = [dep_name]

    _yaml.roundtrip_dump(element, element_path)


def generate_import_element(tmpdir, kind, project, name):
    element_name = "import-{}.bst".format(name)
    repo_element_path = os.path.join(project, "elements", element_name)
    files = str(tmpdir.join("imported_files_{}".format(name)))
    os.makedirs(files)

    with open(os.path.join(files, "{}.txt".format(name)), "w") as f:
        f.write(name)

    repo = create_repo(kind, str(tmpdir.join("element_{}_repo".format(name))))
    repo.create(files)

    generate_element(repo, repo_element_path)

    return element_name


def generate_project(tmpdir, name, kind, config=None):
    if config is None:
        config = {}

    project_name = "project-{}".format(name)
    subproject_path = os.path.join(str(tmpdir.join(project_name)))
    os.makedirs(os.path.join(subproject_path, "elements"))

    project_conf = {"name": name, "min-version": "2.0", "element-path": "elements"}
    project_conf.update(config)
    _yaml.roundtrip_dump(project_conf, os.path.join(subproject_path, "project.conf"))
    add_plugins_conf(subproject_path, kind)

    return project_name, subproject_path


def generate_simple_stack(project, name, dependencies):
    element_name = "{}.bst".format(name)
    element_path = os.path.join(project, "elements", element_name)
    element = {"kind": "stack", "depends": dependencies}
    _yaml.roundtrip_dump(element, element_path)

    return element_name


def generate_cross_element(project, subproject_name, import_name):
    basename, _ = os.path.splitext(import_name)
    return generate_simple_stack(
        project,
        "import-{}-{}".format(subproject_name, basename),
        [{"junction": "{}.bst".format(subproject_name), "filename": import_name}],
    )


@pytest.mark.parametrize("kind", ALL_REPO_KINDS.keys())
def test_cross_junction_multiple_projects(cli, tmpdir, kind):
    tmpdir = tmpdir.join(kind)

    # Generate 3 projects: main, a, b
    _, project = generate_project(tmpdir, "main", kind, {"ref-storage": "project.refs"})
    project_a, project_a_path = generate_project(tmpdir, "a", kind)
    project_b, project_b_path = generate_project(tmpdir, "b", kind)

    # Generate an element with a trackable source for each project
    element_a = generate_import_element(tmpdir, kind, project_a_path, "a")
    element_b = generate_import_element(tmpdir, kind, project_b_path, "b")
    element_c = generate_import_element(tmpdir, kind, project, "c")

    # Create some indirections to the elements with dependencies to test --deps
    stack_a = generate_simple_stack(project_a_path, "stack-a", [element_a])
    stack_b = generate_simple_stack(project_b_path, "stack-b", [element_b])

    # Create junctions for projects a and b in main.
    junction_a = "{}.bst".format(project_a)
    junction_a_path = os.path.join(project, "elements", junction_a)
    generate_junction(tmpdir.join("repo_a"), project_a_path, junction_a_path, store_ref=False)

    junction_b = "{}.bst".format(project_b)
    junction_b_path = os.path.join(project, "elements", junction_b)
    generate_junction(tmpdir.join("repo_b"), project_b_path, junction_b_path, store_ref=False)

    # Track the junctions.
    result = cli.run(project=project, args=["source", "track", junction_a, junction_b])
    result.assert_success()

    # Import elements from a and b in to main.
    imported_a = generate_cross_element(project, project_a, stack_a)
    imported_b = generate_cross_element(project, project_b, stack_b)

    # Generate a top level stack depending on everything
    all_bst = generate_simple_stack(project, "all", [imported_a, imported_b, element_c])

    # Track without following junctions. But explicitly also track the elements in project a.
    result = cli.run(
        project=project, args=["source", "track", "--deps", "all", all_bst, "{}:{}".format(junction_a, stack_a)]
    )
    result.assert_success()

    # Elements in project b should not be tracked. But elements in project a and main should.
    expected = [element_c, "{}:{}".format(junction_a, element_a)]
    assert set(result.get_tracked_elements()) == set(expected)


@pytest.mark.parametrize("kind", ALL_REPO_KINDS.keys())
def test_track_exceptions(cli, tmpdir, kind):
    tmpdir = tmpdir.join(kind)

    _, project = generate_project(tmpdir, "main", kind, {"ref-storage": "project.refs"})
    project_a, project_a_path = generate_project(tmpdir, "a", kind)

    element_a = generate_import_element(tmpdir, kind, project_a_path, "a")
    element_b = generate_import_element(tmpdir, kind, project_a_path, "b")

    all_bst = generate_simple_stack(project_a_path, "all", [element_a, element_b])

    junction_a = "{}.bst".format(project_a)
    junction_a_path = os.path.join(project, "elements", junction_a)
    generate_junction(tmpdir.join("repo_a"), project_a_path, junction_a_path, store_ref=False)

    result = cli.run(project=project, args=["source", "track", junction_a])
    result.assert_success()

    imported_b = generate_cross_element(project, project_a, element_b)
    indirection = generate_simple_stack(project, "indirection", [imported_b])

    result = cli.run(
        project=project,
        args=[
            "source",
            "track",
            "--deps",
            "all",
            "--except",
            indirection,
            "{}:{}".format(junction_a, all_bst),
            imported_b,
        ],
    )
    result.assert_success()

    expected = ["{}:{}".format(junction_a, element_a), "{}:{}".format(junction_a, element_b)]
    assert set(result.get_tracked_elements()) == set(expected)
