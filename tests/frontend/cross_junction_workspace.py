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
from buildstream._testing import cli  # pylint: disable=unused-import
from buildstream._testing import create_repo
from buildstream import _yaml


def prepare_junction_project(cli, tmpdir):
    main_project = tmpdir.join("main")
    sub_project = tmpdir.join("sub")
    os.makedirs(str(main_project))
    os.makedirs(str(sub_project))

    _yaml.roundtrip_dump({"name": "main", "min-version": "2.0"}, str(main_project.join("project.conf")))
    _yaml.roundtrip_dump({"name": "sub", "min-version": "2.0"}, str(sub_project.join("project.conf")))

    import_dir = tmpdir.join("import")
    os.makedirs(str(import_dir))
    with open(str(import_dir.join("hello.txt")), "w", encoding="utf-8") as f:
        f.write("hello!")

    import_repo_dir = tmpdir.join("import_repo")
    os.makedirs(str(import_repo_dir))
    import_repo = create_repo("tar", str(import_repo_dir))
    import_ref = import_repo.create(str(import_dir))

    _yaml.roundtrip_dump(
        {"kind": "import", "sources": [import_repo.source_config(ref=import_ref)]}, str(sub_project.join("data.bst"))
    )

    sub_repo_dir = tmpdir.join("sub_repo")
    os.makedirs(str(sub_repo_dir))
    sub_repo = create_repo("tar", str(sub_repo_dir))
    sub_ref = sub_repo.create(str(sub_project))

    _yaml.roundtrip_dump(
        {"kind": "junction", "sources": [sub_repo.source_config(ref=sub_ref)]}, str(main_project.join("sub.bst"))
    )

    args = ["source", "fetch", "sub.bst"]
    result = cli.run(project=str(main_project), args=args)
    result.assert_success()

    return str(main_project)


def open_cross_junction(cli, tmpdir):
    project = prepare_junction_project(cli, tmpdir)
    element = "sub.bst:data.bst"

    oldkey = cli.get_element_key(project, element)

    workspace = tmpdir.join("workspace")
    args = ["workspace", "open", "--directory", str(workspace), element]
    result = cli.run(project=project, args=args)
    result.assert_success()

    assert cli.get_element_state(project, element) == "buildable"
    assert os.path.exists(str(workspace.join("hello.txt")))
    assert cli.get_element_key(project, element) != oldkey

    return project, workspace


def test_open_cross_junction(cli, tmpdir):
    open_cross_junction(cli, tmpdir)


def test_list_cross_junction(cli, tmpdir):
    project, _ = open_cross_junction(cli, tmpdir)

    element = "sub.bst:data.bst"

    args = ["workspace", "list"]
    result = cli.run(project=project, args=args)
    result.assert_success()

    loaded = _yaml.load_data(result.output)
    workspaces = loaded.get_sequence("workspaces")
    assert len(workspaces) == 1
    first_workspace = workspaces.mapping_at(0)

    assert "element" in first_workspace
    assert first_workspace.get_str("element") == element


def test_close_cross_junction(cli, tmpdir):
    project, workspace = open_cross_junction(cli, tmpdir)

    element = "sub.bst:data.bst"
    args = ["workspace", "close", "--remove-dir", element]
    result = cli.run(project=project, args=args)
    result.assert_success()

    assert not os.path.exists(str(workspace))

    args = ["workspace", "list"]
    result = cli.run(project=project, args=args)
    result.assert_success()

    loaded = _yaml.load_data(result.output)
    workspaces = loaded.get_sequence("workspaces")
    assert not workspaces


def test_close_all_cross_junction(cli, tmpdir):
    project, workspace = open_cross_junction(cli, tmpdir)

    args = ["workspace", "close", "--remove-dir", "--all"]
    result = cli.run(project=project, args=args)
    result.assert_success()

    assert not os.path.exists(str(workspace))

    args = ["workspace", "list"]
    result = cli.run(project=project, args=args)
    result.assert_success()

    loaded = _yaml.load_data(result.output)
    workspaces = loaded.get_sequence("workspaces")
    assert not workspaces


def test_subdir_command_cross_junction(cli, tmpdir):
    # i.e. commands can be run successfully from a subdirectory of the
    # junction's workspace, in case project loading logic has gone wrong
    project = prepare_junction_project(cli, tmpdir)
    workspace = os.path.join(str(tmpdir), "workspace")
    junction_element = "sub.bst"

    # Open the junction as a workspace
    args = ["workspace", "open", "--directory", workspace, junction_element]
    result = cli.run(project=project, args=args)
    result.assert_success()

    # Run commands from a subdirectory of the workspace
    newdir = os.path.join(str(workspace), "newdir")
    element_name = "data.bst"
    os.makedirs(newdir)
    result = cli.run(project=str(workspace), args=["-C", newdir, "show", element_name])
    result.assert_success()
