#
#  Copyright (C) 2018 Codethink Limited
#  Copyright (C) 2018 Bloomberg Finance LP
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
#  Authors: Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
#           Tristan Maat <tristan.maat@codethink.co.uk>
#           Chandan Singh <csingh43@bloomberg.net>
#           Phillip Smyth <phillip.smyth@codethink.co.uk>
#           Jonathan Maw <jonathan.maw@codethink.co.uk>
#           Richard Maw <richard.maw@codethink.co.uk>
#           William Salmon <will.salmon@codethink.co.uk>
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import stat
import shutil
import subprocess

import pytest

from buildstream.testing import create_repo, ALL_REPO_KINDS
from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream import _yaml
from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream._workspaces import BST_WORKSPACE_FORMAT_VERSION

from tests.testutils import create_artifact_share, create_element_size, wait_for_cache_granularity

repo_kinds = ALL_REPO_KINDS

# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project",)
BASE_FILENAME = os.path.basename(__file__)


class WorkspaceCreator:
    def __init__(self, cli, tmpdir, datafiles, project_path=None):
        self.cli = cli
        self.tmpdir = tmpdir
        self.datafiles = datafiles

        if not project_path:
            project_path = str(datafiles)
        else:
            shutil.copytree(str(datafiles), project_path)

        self.project_path = project_path
        self.bin_files_path = os.path.join(project_path, "files", "bin-files")

        self.workspace_cmd = os.path.join(self.project_path, "workspace_cmd")

    def create_workspace_element(self, kind, suffix="", workspace_dir=None, element_attrs=None):
        element_name = "workspace-test-{}{}.bst".format(kind, suffix)
        element_path = os.path.join(self.project_path, "elements")
        if not workspace_dir:
            workspace_dir = os.path.join(self.workspace_cmd, element_name)
            if workspace_dir[-4:] == ".bst":
                workspace_dir = workspace_dir[:-4]

        # Create our repo object of the given source type with
        # the bin files, and then collect the initial ref.
        repo = create_repo(kind, str(self.tmpdir))
        ref = repo.create(self.bin_files_path)

        # Write out our test target
        element = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
        if element_attrs:
            element = {**element, **element_attrs}
        _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))
        return element_name, element_path, workspace_dir

    def create_workspace_elements(self, kinds, suffixs=None, workspace_dir_usr=None, element_attrs=None):

        element_tuples = []

        if suffixs is None:
            suffixs = ["",] * len(kinds)
        else:
            if len(suffixs) != len(kinds):
                raise "terable error"

        for suffix, kind in zip(suffixs, kinds):
            element_name, _, workspace_dir = self.create_workspace_element(
                kind, suffix, workspace_dir_usr, element_attrs
            )
            element_tuples.append((element_name, workspace_dir))

        # Assert that there is a fetch is needed
        states = self.cli.get_element_states(self.project_path, [e for e, _ in element_tuples])
        assert not any(states[e] != "fetch needed" for e, _ in element_tuples)

        return element_tuples

    def open_workspaces(self, kinds, suffixs=None, workspace_dir=None, element_attrs=None, no_checkout=False):

        element_tuples = self.create_workspace_elements(kinds, suffixs, workspace_dir, element_attrs)
        os.makedirs(self.workspace_cmd, exist_ok=True)

        # Now open the workspace, this should have the effect of automatically
        # tracking & fetching the source from the repo.
        args = ["workspace", "open"]
        if no_checkout:
            args.append("--no-checkout")
        if workspace_dir is not None:
            assert len(element_tuples) == 1, "test logic error"
            _, workspace_dir = element_tuples[0]
            args.extend(["--directory", workspace_dir])

        args.extend([element_name for element_name, workspace_dir_suffix in element_tuples])
        result = self.cli.run(cwd=self.workspace_cmd, project=self.project_path, args=args)

        result.assert_success()

        if not no_checkout:
            # Assert that we are now buildable because the source is now cached.
            states = self.cli.get_element_states(self.project_path, [e for e, _ in element_tuples])
            assert not any(states[e] != "buildable" for e, _ in element_tuples)

            # Check that the executable hello file is found in each workspace
            for _, workspace in element_tuples:
                filename = os.path.join(workspace, "usr", "bin", "hello")
                assert os.path.exists(filename)

        return element_tuples


def open_workspace(
    cli,
    tmpdir,
    datafiles,
    kind,
    suffix="",
    workspace_dir=None,
    project_path=None,
    element_attrs=None,
    no_checkout=False,
):
    workspace_object = WorkspaceCreator(cli, tmpdir, datafiles, project_path)
    workspaces = workspace_object.open_workspaces((kind,), (suffix,), workspace_dir, element_attrs, no_checkout)
    assert len(workspaces) == 1
    element_name, workspace = workspaces[0]
    return element_name, workspace_object.project_path, workspace


@pytest.mark.datafiles(DATA_DIR)
def test_open_bzr_customize(cli, tmpdir, datafiles):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, "bzr")

    # Check that the .bzr dir exists
    bzrdir = os.path.join(workspace, ".bzr")
    assert os.path.isdir(bzrdir)

    # Check that the correct origin branch is set
    element_config = _yaml.load(os.path.join(project, "elements", element_name), shortname=None)
    source_config = element_config.get_sequence("sources").mapping_at(0)
    output = subprocess.check_output(["bzr", "info"], cwd=workspace)
    stripped_url = source_config.get_str("url").lstrip("file:///")
    expected_output_str = "checkout of branch: /{}/{}".format(stripped_url, source_config.get_str("track"))
    assert expected_output_str in str(output)


@pytest.mark.datafiles(DATA_DIR)
def test_open_multi(cli, tmpdir, datafiles):

    workspace_object = WorkspaceCreator(cli, tmpdir, datafiles)
    workspaces = workspace_object.open_workspaces(repo_kinds)

    for (elname, workspace), kind in zip(workspaces, repo_kinds):
        assert kind in elname
        workspace_lsdir = os.listdir(workspace)
        if kind == "git":
            assert ".git" in workspace_lsdir
        elif kind == "bzr":
            assert ".bzr" in workspace_lsdir
        else:
            assert ".git" not in workspace_lsdir
            assert ".bzr" not in workspace_lsdir


@pytest.mark.skipif(os.geteuid() == 0, reason="root may have CAP_DAC_OVERRIDE and ignore permissions")
@pytest.mark.datafiles(DATA_DIR)
def test_open_multi_unwritable(cli, tmpdir, datafiles):
    workspace_object = WorkspaceCreator(cli, tmpdir, datafiles)

    element_tuples = workspace_object.create_workspace_elements(repo_kinds, repo_kinds)
    os.makedirs(workspace_object.workspace_cmd, exist_ok=True)

    # Now open the workspace, this should have the effect of automatically
    # tracking & fetching the source from the repo.
    args = ["workspace", "open"]
    args.extend([element_name for element_name, workspace_dir_suffix in element_tuples])
    cli.configure({"workspacedir": workspace_object.workspace_cmd})

    cwdstat = os.stat(workspace_object.workspace_cmd)
    try:
        os.chmod(workspace_object.workspace_cmd, cwdstat.st_mode - stat.S_IWRITE)
        result = workspace_object.cli.run(project=workspace_object.project_path, args=args)
    finally:
        # Using this finally to make sure we always put thing back how they should be.
        os.chmod(workspace_object.workspace_cmd, cwdstat.st_mode)

    result.assert_main_error(ErrorDomain.STREAM, None)
    # Normally we avoid checking stderr in favour of using the mechine readable result.assert_main_error
    # But Tristan was very keen that the names of the elements left needing workspaces were present in the out put
    assert " ".join([element_name for element_name, workspace_dir_suffix in element_tuples[1:]]) in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_open_multi_with_directory(cli, tmpdir, datafiles):
    workspace_object = WorkspaceCreator(cli, tmpdir, datafiles)

    element_tuples = workspace_object.create_workspace_elements(repo_kinds, repo_kinds)
    os.makedirs(workspace_object.workspace_cmd, exist_ok=True)

    # Now open the workspace, this should have the effect of automatically
    # tracking & fetching the source from the repo.
    args = ["workspace", "open"]
    args.extend(["--directory", "any/dir/should/fail"])

    args.extend([element_name for element_name, workspace_dir_suffix in element_tuples])
    result = workspace_object.cli.run(
        cwd=workspace_object.workspace_cmd, project=workspace_object.project_path, args=args
    )

    result.assert_main_error(ErrorDomain.STREAM, "directory-with-multiple-elements")


@pytest.mark.datafiles(DATA_DIR)
def test_open_defaultlocation(cli, tmpdir, datafiles):
    workspace_object = WorkspaceCreator(cli, tmpdir, datafiles)

    # pylint: disable=unbalanced-tuple-unpacking
    ((element_name, workspace_dir),) = workspace_object.create_workspace_elements(["git"], ["git"])
    os.makedirs(workspace_object.workspace_cmd, exist_ok=True)

    # Now open the workspace, this should have the effect of automatically
    # tracking & fetching the source from the repo.
    args = ["workspace", "open"]
    args.append(element_name)

    # In the other tests we set the cmd to workspace_object.workspace_cmd with the optional
    # argument, cwd for the workspace_object.cli.run function. But hear we set the default
    # workspace location to workspace_object.workspace_cmd and run the cli.run function with
    # no cwd option so that it runs in the project directory.
    cli.configure({"workspacedir": workspace_object.workspace_cmd})
    result = workspace_object.cli.run(project=workspace_object.project_path, args=args)

    result.assert_success()

    assert cli.get_element_state(workspace_object.project_path, element_name) == "buildable"

    # Check that the executable hello file is found in the workspace
    # even though the cli.run function was not run with cwd = workspace_object.workspace_cmd
    # the workspace should be created in there as we used the 'workspacedir' configuration
    # option.
    filename = os.path.join(workspace_dir, "usr", "bin", "hello")
    assert os.path.exists(filename)


@pytest.mark.datafiles(DATA_DIR)
def test_open_defaultlocation_exists(cli, tmpdir, datafiles):
    workspace_object = WorkspaceCreator(cli, tmpdir, datafiles)

    # pylint: disable=unbalanced-tuple-unpacking
    ((element_name, workspace_dir),) = workspace_object.create_workspace_elements(["git"], ["git"])
    os.makedirs(workspace_object.workspace_cmd, exist_ok=True)

    with open(workspace_dir, "w") as fl:
        fl.write("foo")

    # Now open the workspace, this should have the effect of automatically
    # tracking & fetching the source from the repo.
    args = ["workspace", "open"]
    args.append(element_name)

    # In the other tests we set the cmd to workspace_object.workspace_cmd with the optional
    # argument, cwd for the workspace_object.cli.run function. But hear we set the default
    # workspace location to workspace_object.workspace_cmd and run the cli.run function with
    # no cwd option so that it runs in the project directory.
    cli.configure({"workspacedir": workspace_object.workspace_cmd})
    result = workspace_object.cli.run(project=workspace_object.project_path, args=args)

    result.assert_main_error(ErrorDomain.STREAM, "bad-directory")


@pytest.mark.datafiles(DATA_DIR)
def test_open_track(cli, tmpdir, datafiles):
    open_workspace(cli, tmpdir, datafiles, "git")


@pytest.mark.datafiles(DATA_DIR)
def test_open_noclose_open(cli, tmpdir, datafiles):
    # opening the same workspace twice without closing it should fail
    element_name, project, _ = open_workspace(cli, tmpdir, datafiles, "git")

    result = cli.run(project=project, args=["workspace", "open", element_name])
    result.assert_main_error(ErrorDomain.STREAM, None)


@pytest.mark.datafiles(DATA_DIR)
def test_open_force(cli, tmpdir, datafiles):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, "git")

    # Close the workspace
    result = cli.run(project=project, args=["workspace", "close", element_name])
    result.assert_success()

    # Assert the workspace dir still exists
    assert os.path.exists(workspace)

    # Now open the workspace again with --force, this should happily succeed
    result = cli.run(project=project, args=["workspace", "open", "--force", "--directory", workspace, element_name])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
def test_open_force_open(cli, tmpdir, datafiles):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, "git")

    result = cli.run(project=project, args=["workspace", "close", element_name])
    result.assert_success()

    # Assert the workspace dir exists
    assert os.path.exists(workspace)

    # Now open the workspace again with --force, this should happily succeed
    result = cli.run(project=project, args=["workspace", "open", "--force", "--directory", workspace, element_name])
    result.assert_success()


# Regression test for #1086.
@pytest.mark.datafiles(DATA_DIR)
def test_open_force_open_no_checkout(cli, tmpdir, datafiles):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, "git")
    hello_path = os.path.join(workspace, "hello.txt")

    # Assert the workspace dir exists
    assert os.path.exists(workspace)

    # Create a new file in the workspace
    with open(hello_path, "w") as f:
        f.write("hello")

    # Now open the workspace again with --force and --no-checkout
    result = cli.run(
        project=project, args=["workspace", "open", "--force", "--no-checkout", "--directory", workspace, element_name]
    )
    result.assert_success()

    # Ensure that our files were not overwritten
    assert os.path.exists(hello_path)
    with open(hello_path) as f:
        assert f.read() == "hello"


@pytest.mark.datafiles(DATA_DIR)
def test_open_force_different_workspace(cli, tmpdir, datafiles):
    _, project, workspace = open_workspace(cli, tmpdir, datafiles, "git", "-alpha")

    # Assert the workspace dir exists
    assert os.path.exists(workspace)

    hello_path = os.path.join(workspace, "usr", "bin", "hello")
    hello1_path = os.path.join(workspace, "usr", "bin", "hello1")

    tmpdir = os.path.join(str(tmpdir), "-beta")
    shutil.move(hello_path, hello1_path)
    element_name2, _, workspace2 = open_workspace(cli, tmpdir, datafiles, "git", "-beta")

    # Assert the workspace dir exists
    assert os.path.exists(workspace2)

    # Assert that workspace 1 contains the modified file
    assert os.path.exists(hello1_path)

    # Assert that workspace 2 contains the unmodified file
    assert os.path.exists(os.path.join(workspace2, "usr", "bin", "hello"))

    result = cli.run(project=project, args=["workspace", "close", element_name2])
    result.assert_success()

    # Now open the workspace again with --force, this should happily succeed
    result = cli.run(project=project, args=["workspace", "open", "--force", "--directory", workspace, element_name2])
    result.assert_success()

    # Assert that the file in workspace 1 has been replaced
    # With the file from workspace 2
    assert os.path.exists(hello_path)
    assert not os.path.exists(hello1_path)


@pytest.mark.datafiles(DATA_DIR)
def test_close(cli, tmpdir, datafiles):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, "git")

    # Close the workspace
    result = cli.run(project=project, args=["workspace", "close", "--remove-dir", element_name])
    result.assert_success()

    # Assert the workspace dir has been deleted
    assert not os.path.exists(workspace)


@pytest.mark.datafiles(DATA_DIR)
def test_close_external_after_move_project(cli, tmpdir, datafiles):
    workspace_dir = os.path.join(str(tmpdir), "workspace")
    project_path = os.path.join(str(tmpdir), "initial_project")
    element_name, _, _ = open_workspace(cli, tmpdir, datafiles, "git", "", workspace_dir, project_path)
    assert os.path.exists(workspace_dir)
    moved_dir = os.path.join(str(tmpdir), "external_project")
    shutil.move(project_path, moved_dir)
    assert os.path.exists(moved_dir)

    # Close the workspace
    result = cli.run(project=moved_dir, args=["workspace", "close", "--remove-dir", element_name])
    result.assert_success()

    # Assert the workspace dir has been deleted
    assert not os.path.exists(workspace_dir)


@pytest.mark.datafiles(DATA_DIR)
def test_close_internal_after_move_project(cli, tmpdir, datafiles):
    initial_dir = os.path.join(str(tmpdir), "initial_project")
    initial_workspace = os.path.join(initial_dir, "workspace")
    element_name, _, _ = open_workspace(
        cli, tmpdir, datafiles, "git", workspace_dir=initial_workspace, project_path=initial_dir
    )
    moved_dir = os.path.join(str(tmpdir), "internal_project")
    shutil.move(initial_dir, moved_dir)
    assert os.path.exists(moved_dir)

    # Close the workspace
    result = cli.run(project=moved_dir, args=["workspace", "close", "--remove-dir", element_name])
    result.assert_success()

    # Assert the workspace dir has been deleted
    workspace = os.path.join(moved_dir, "workspace")
    assert not os.path.exists(workspace)


@pytest.mark.datafiles(DATA_DIR)
def test_close_removed(cli, tmpdir, datafiles):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, "git")

    # Remove it first, closing the workspace should work
    shutil.rmtree(workspace)

    # Close the workspace
    result = cli.run(project=project, args=["workspace", "close", element_name])
    result.assert_success()

    # Assert the workspace dir has been deleted
    assert not os.path.exists(workspace)


@pytest.mark.datafiles(DATA_DIR)
def test_close_nonexistant_element(cli, tmpdir, datafiles):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, "git")
    element_path = os.path.join(datafiles.dirname, datafiles.basename, "elements", element_name)

    # First brutally remove the element.bst file, ensuring that
    # the element does not exist anymore in the project where
    # we want to close the workspace.
    os.remove(element_path)

    # Close the workspace
    result = cli.run(project=project, args=["workspace", "close", "--remove-dir", element_name])
    result.assert_success()

    # Assert the workspace dir has been deleted
    assert not os.path.exists(workspace)


@pytest.mark.datafiles(DATA_DIR)
def test_close_multiple(cli, tmpdir, datafiles):
    tmpdir_alpha = os.path.join(str(tmpdir), "alpha")
    tmpdir_beta = os.path.join(str(tmpdir), "beta")
    alpha, project, workspace_alpha = open_workspace(cli, tmpdir_alpha, datafiles, "git", suffix="-alpha")
    beta, project, workspace_beta = open_workspace(cli, tmpdir_beta, datafiles, "git", suffix="-beta")

    # Close the workspaces
    result = cli.run(project=project, args=["workspace", "close", "--remove-dir", alpha, beta])
    result.assert_success()

    # Assert the workspace dirs have been deleted
    assert not os.path.exists(workspace_alpha)
    assert not os.path.exists(workspace_beta)


@pytest.mark.datafiles(DATA_DIR)
def test_close_all(cli, tmpdir, datafiles):
    tmpdir_alpha = os.path.join(str(tmpdir), "alpha")
    tmpdir_beta = os.path.join(str(tmpdir), "beta")
    _, project, workspace_alpha = open_workspace(cli, tmpdir_alpha, datafiles, "git", suffix="-alpha")
    _, project, workspace_beta = open_workspace(cli, tmpdir_beta, datafiles, "git", suffix="-beta")

    # Close the workspaces
    result = cli.run(project=project, args=["workspace", "close", "--remove-dir", "--all"])
    result.assert_success()

    # Assert the workspace dirs have been deleted
    assert not os.path.exists(workspace_alpha)
    assert not os.path.exists(workspace_beta)


@pytest.mark.datafiles(DATA_DIR)
def test_reset(cli, tmpdir, datafiles):
    # Open the workspace
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, "git")

    # Modify workspace
    shutil.rmtree(os.path.join(workspace, "usr", "bin"))
    os.makedirs(os.path.join(workspace, "etc"))
    with open(os.path.join(workspace, "etc", "pony.conf"), "w") as f:
        f.write("PONY='pink'")

    # Now reset the open workspace, this should have the
    # effect of reverting our changes.
    result = cli.run(project=project, args=["workspace", "reset", element_name])
    result.assert_success()
    assert os.path.exists(os.path.join(workspace, "usr", "bin", "hello"))
    assert not os.path.exists(os.path.join(workspace, "etc", "pony.conf"))


@pytest.mark.datafiles(DATA_DIR)
def test_reset_soft(cli, tmpdir, datafiles):
    # Open the workspace
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, "git")

    assert cli.get_element_state(project, element_name) == "buildable"

    hello_path = os.path.join(workspace, "usr", "bin", "hello")
    pony_path = os.path.join(workspace, "etc", "pony.conf")

    assert os.path.exists(os.path.join(workspace, "usr", "bin"))
    assert os.path.exists(hello_path)
    assert not os.path.exists(pony_path)

    key_1 = cli.get_element_key(project, element_name)
    assert key_1 != "{:?<64}".format("")
    result = cli.run(project=project, args=["build", element_name])
    result.assert_success()
    assert cli.get_element_state(project, element_name) == "cached"
    key_2 = cli.get_element_key(project, element_name)
    assert key_2 != "{:?<64}".format("")

    # workspace keys are not recalculated
    assert key_1 == key_2

    wait_for_cache_granularity()

    # Modify workspace
    shutil.rmtree(os.path.join(workspace, "usr", "bin"))
    os.makedirs(os.path.join(workspace, "etc"))
    with open(os.path.join(workspace, "etc", "pony.conf"), "w") as f:
        f.write("PONY='pink'")

    assert not os.path.exists(os.path.join(workspace, "usr", "bin"))
    assert os.path.exists(pony_path)

    # Now soft-reset the open workspace, this should not revert the changes
    result = cli.run(project=project, args=["workspace", "reset", "--soft", element_name])
    result.assert_success()
    # we removed this dir
    assert not os.path.exists(os.path.join(workspace, "usr", "bin"))
    # and added this one
    assert os.path.exists(os.path.join(workspace, "etc", "pony.conf"))

    assert cli.get_element_state(project, element_name) == "buildable"
    key_3 = cli.get_element_key(project, element_name)
    assert key_3 != "{:?<64}".format("")
    assert key_1 != key_3


@pytest.mark.datafiles(DATA_DIR)
def test_reset_multiple(cli, tmpdir, datafiles):
    # Open the workspaces
    tmpdir_alpha = os.path.join(str(tmpdir), "alpha")
    tmpdir_beta = os.path.join(str(tmpdir), "beta")
    alpha, project, workspace_alpha = open_workspace(cli, tmpdir_alpha, datafiles, "git", suffix="-alpha")
    beta, project, workspace_beta = open_workspace(cli, tmpdir_beta, datafiles, "git", suffix="-beta")

    # Modify workspaces
    shutil.rmtree(os.path.join(workspace_alpha, "usr", "bin"))
    os.makedirs(os.path.join(workspace_beta, "etc"))
    with open(os.path.join(workspace_beta, "etc", "pony.conf"), "w") as f:
        f.write("PONY='pink'")

    # Now reset the open workspaces, this should have the
    # effect of reverting our changes.
    result = cli.run(project=project, args=["workspace", "reset", alpha, beta,])
    result.assert_success()
    assert os.path.exists(os.path.join(workspace_alpha, "usr", "bin", "hello"))
    assert not os.path.exists(os.path.join(workspace_beta, "etc", "pony.conf"))


@pytest.mark.datafiles(DATA_DIR)
def test_reset_all(cli, tmpdir, datafiles):
    # Open the workspaces
    tmpdir_alpha = os.path.join(str(tmpdir), "alpha")
    tmpdir_beta = os.path.join(str(tmpdir), "beta")
    _, project, workspace_alpha = open_workspace(cli, tmpdir_alpha, datafiles, "git", suffix="-alpha")
    _, project, workspace_beta = open_workspace(cli, tmpdir_beta, datafiles, "git", suffix="-beta")

    # Modify workspaces
    shutil.rmtree(os.path.join(workspace_alpha, "usr", "bin"))
    os.makedirs(os.path.join(workspace_beta, "etc"))
    with open(os.path.join(workspace_beta, "etc", "pony.conf"), "w") as f:
        f.write("PONY='pink'")

    # Now reset the open workspace, this should have the
    # effect of reverting our changes.
    result = cli.run(project=project, args=["workspace", "reset", "--all"])
    result.assert_success()
    assert os.path.exists(os.path.join(workspace_alpha, "usr", "bin", "hello"))
    assert not os.path.exists(os.path.join(workspace_beta, "etc", "pony.conf"))


@pytest.mark.datafiles(DATA_DIR)
def test_list(cli, tmpdir, datafiles):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, "git")

    # Now list the workspaces
    result = cli.run(project=project, args=["workspace", "list"])
    result.assert_success()

    loaded = _yaml.load_data(result.output)
    workspaces = loaded.get_sequence("workspaces")
    assert len(workspaces) == 1

    space = workspaces.mapping_at(0)
    assert space.get_str("element") == element_name
    assert space.get_str("directory") == workspace


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", repo_kinds)
@pytest.mark.parametrize("strict", [("strict"), ("non-strict")])
@pytest.mark.parametrize(
    "from_workspace,guess_element",
    [(False, False), (True, True), (True, False)],
    ids=["project-no-guess", "workspace-guess", "workspace-no-guess"],
)
def test_build(cli, tmpdir_factory, datafiles, kind, strict, from_workspace, guess_element):
    tmpdir = tmpdir_factory.mktemp(BASE_FILENAME)
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, kind, False)
    checkout = os.path.join(str(tmpdir), "checkout")
    args_dir = ["-C", workspace] if from_workspace else []
    args_elm = [element_name] if not guess_element else []

    # Modify workspace
    shutil.rmtree(os.path.join(workspace, "usr", "bin"))
    os.makedirs(os.path.join(workspace, "etc"))
    with open(os.path.join(workspace, "etc", "pony.conf"), "w") as f:
        f.write("PONY='pink'")

    # Configure strict mode
    strict_mode = True
    if strict != "strict":
        strict_mode = False
    cli.configure({"projects": {"test": {"strict": strict_mode}}})

    # Build modified workspace
    assert cli.get_element_state(project, element_name) == "buildable"
    key_1 = cli.get_element_key(project, element_name)
    assert key_1 != "{:?<64}".format("")
    result = cli.run(project=project, args=args_dir + ["build", *args_elm])
    result.assert_success()
    assert cli.get_element_state(project, element_name) == "cached"
    key_2 = cli.get_element_key(project, element_name)
    assert key_2 != "{:?<64}".format("")

    # workspace keys are not recalculated
    assert key_1 == key_2

    # Checkout the result
    result = cli.run(project=project, args=args_dir + ["artifact", "checkout", "--directory", checkout, *args_elm])
    result.assert_success()

    # Check that the pony.conf from the modified workspace exists
    filename = os.path.join(checkout, "etc", "pony.conf")
    assert os.path.exists(filename)

    # Check that the original /usr/bin/hello is not in the checkout
    assert not os.path.exists(os.path.join(checkout, "usr", "bin", "hello"))


@pytest.mark.datafiles(DATA_DIR)
def test_buildable_no_ref(cli, tmpdir, datafiles):
    project = str(datafiles)
    element_name = "workspace-test-no-ref.bst"
    element_path = os.path.join(project, "elements")

    # Write out our test target without any source ref
    repo = create_repo("git", str(tmpdir))
    element = {"kind": "import", "sources": [repo.source_config()]}
    _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

    # Assert that this target is not buildable when no workspace is associated.
    assert cli.get_element_state(project, element_name) == "no reference"

    # Now open the workspace. We don't need to checkout the source though.
    workspace = os.path.join(str(tmpdir), "workspace-no-ref")
    os.makedirs(workspace)
    args = ["workspace", "open", "--no-checkout", "--directory", workspace, element_name]
    result = cli.run(project=project, args=args)
    result.assert_success()

    # Assert that the target is now buildable.
    assert cli.get_element_state(project, element_name) == "buildable"


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("modification", [("addfile"), ("removefile"), ("modifyfile")])
@pytest.mark.parametrize("strict", [("strict"), ("non-strict")])
def test_detect_modifications(cli, tmpdir, datafiles, modification, strict):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, "git")
    checkout = os.path.join(str(tmpdir), "checkout")

    # Configure strict mode
    strict_mode = True
    if strict != "strict":
        strict_mode = False
    cli.configure({"projects": {"test": {"strict": strict_mode}}})

    # Build clean workspace
    assert cli.get_element_state(project, element_name) == "buildable"
    key_1 = cli.get_element_key(project, element_name)
    assert key_1 != "{:?<64}".format("")
    result = cli.run(project=project, args=["build", element_name])
    result.assert_success()
    assert cli.get_element_state(project, element_name) == "cached"
    key_2 = cli.get_element_key(project, element_name)
    assert key_2 != "{:?<64}".format("")

    # workspace keys are not recalculated
    assert key_1 == key_2

    wait_for_cache_granularity()

    # Modify the workspace in various different ways, ensuring we
    # properly detect the changes.
    #
    if modification == "addfile":
        os.makedirs(os.path.join(workspace, "etc"))
        with open(os.path.join(workspace, "etc", "pony.conf"), "w") as f:
            f.write("PONY='pink'")
    elif modification == "removefile":
        os.remove(os.path.join(workspace, "usr", "bin", "hello"))
    elif modification == "modifyfile":
        with open(os.path.join(workspace, "usr", "bin", "hello"), "w") as f:
            f.write("cookie")
    else:
        # This cannot be reached
        assert 0

    # First assert that the state is properly detected
    assert cli.get_element_state(project, element_name) == "buildable"
    key_3 = cli.get_element_key(project, element_name)
    assert key_3 != "{:?<64}".format("")

    # Since there are different things going on at `bst build` time
    # than `bst show` time, we also want to build / checkout again,
    # and ensure that the result contains what we expect.
    result = cli.run(project=project, args=["build", element_name])
    result.assert_success()
    assert cli.get_element_state(project, element_name) == "cached"
    key_4 = cli.get_element_key(project, element_name)
    assert key_4 != "{:?<64}".format("")

    # workspace keys are not recalculated
    assert key_3 == key_4
    # workspace keys are determined by the files
    assert key_1 != key_3

    # Checkout the result
    result = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    result.assert_success()

    # Check the result for the changes we made
    #
    if modification == "addfile":
        filename = os.path.join(checkout, "etc", "pony.conf")
        assert os.path.exists(filename)
    elif modification == "removefile":
        assert not os.path.exists(os.path.join(checkout, "usr", "bin", "hello"))
    elif modification == "modifyfile":
        with open(os.path.join(workspace, "usr", "bin", "hello"), "r") as f:
            data = f.read()
            assert data == "cookie"
    else:
        # This cannot be reached
        assert 0


# Ensure that various versions that should not be accepted raise a
# LoadError.INVALID_DATA
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "workspace_cfg",
    [
        # Test loading a negative workspace version
        {"format-version": -1},
        # Test loading version 0 with two sources
        {"format-version": 0, "alpha.bst": {0: "/workspaces/bravo", 1: "/workspaces/charlie",}},
        # Test loading a version with decimals
        {"format-version": 0.5},
        # Test loading an unsupported old version
        {"format-version": 3},
        # Test loading a future version
        {"format-version": BST_WORKSPACE_FORMAT_VERSION + 1},
    ],
)
def test_list_unsupported_workspace(cli, datafiles, workspace_cfg):
    project = str(datafiles)
    os.makedirs(os.path.join(project, ".bst"))
    workspace_config_path = os.path.join(project, ".bst", "workspaces.yml")

    _yaml.roundtrip_dump(workspace_cfg, workspace_config_path)

    result = cli.run(project=project, args=["workspace", "list"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


# Ensure that various versions that should be accepted are parsed
# correctly.
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "workspace_cfg,expected",
    [
        # Test loading version 4
        (
            {"format-version": 4, "workspaces": {"alpha.bst": {"path": "/workspaces/bravo"}},},
            {
                "format-version": BST_WORKSPACE_FORMAT_VERSION,
                "workspaces": {"alpha.bst": {"path": "/workspaces/bravo"}},
            },
        ),
    ],
)
def test_list_supported_workspace(cli, tmpdir, datafiles, workspace_cfg, expected):
    def parse_dict_as_yaml(node):
        tempfile = os.path.join(str(tmpdir), "yaml_dump")
        _yaml.roundtrip_dump(node, tempfile)
        return _yaml.load(tempfile, shortname=None).strip_node_info()

    project = str(datafiles)
    os.makedirs(os.path.join(project, ".bst"))
    workspace_config_path = os.path.join(project, ".bst", "workspaces.yml")

    _yaml.roundtrip_dump(workspace_cfg, workspace_config_path)

    # Check that we can still read workspace config that is in old format
    result = cli.run(project=project, args=["workspace", "list"])
    result.assert_success()

    loaded_config = _yaml.load(workspace_config_path, shortname=None).strip_node_info()

    # Check that workspace config remains the same if no modifications
    # to workspaces were made
    assert loaded_config == parse_dict_as_yaml(workspace_cfg)

    # Create a test bst file
    bin_files_path = os.path.join(project, "files", "bin-files")
    element_path = os.path.join(project, "elements")
    element_name = "workspace-test.bst"
    workspace = os.path.join(str(tmpdir), "workspace")

    # Create our repo object of the given source type with
    # the bin files, and then collect the initial ref.
    #
    repo = create_repo("git", str(tmpdir))
    ref = repo.create(bin_files_path)

    # Write out our test target
    element = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

    # Make a change to the workspaces file
    result = cli.run(project=project, args=["workspace", "open", "--directory", workspace, element_name])
    result.assert_success()
    result = cli.run(project=project, args=["workspace", "close", "--remove-dir", element_name])
    result.assert_success()

    # Check that workspace config is converted correctly if necessary
    loaded_config = _yaml.load(workspace_config_path, shortname=None).strip_node_info()
    assert loaded_config == parse_dict_as_yaml(expected)


@pytest.mark.datafiles(DATA_DIR)
def test_inconsitent_pipeline_message(cli, tmpdir, datafiles):
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, "git")

    shutil.rmtree(workspace)

    result = cli.run(project=project, args=["build", element_name])
    result.assert_main_error(ErrorDomain.PIPELINE, "inconsistent-pipeline-workspaced")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("strict", [("strict"), ("non-strict")])
def test_cache_key_workspace_in_dependencies(cli, tmpdir, datafiles, strict):
    checkout = os.path.join(str(tmpdir), "checkout")
    element_name, project, workspace = open_workspace(cli, os.path.join(str(tmpdir), "repo-a"), datafiles, "git")

    element_path = os.path.join(project, "elements")
    back_dep_element_name = "workspace-test-back-dep.bst"

    # Write out our test target
    element = {"kind": "compose", "depends": [{"filename": element_name, "type": "build"}]}
    _yaml.roundtrip_dump(element, os.path.join(element_path, back_dep_element_name))

    # Modify workspace
    shutil.rmtree(os.path.join(workspace, "usr", "bin"))
    os.makedirs(os.path.join(workspace, "etc"))
    with open(os.path.join(workspace, "etc", "pony.conf"), "w") as f:
        f.write("PONY='pink'")

    # Configure strict mode
    strict_mode = True
    if strict != "strict":
        strict_mode = False
    cli.configure({"projects": {"test": {"strict": strict_mode}}})

    # Build artifact with dependency's modified workspace
    assert cli.get_element_state(project, element_name) == "buildable"
    key_a1 = cli.get_element_key(project, element_name)
    assert key_a1 != "{:?<64}".format("")
    assert cli.get_element_state(project, back_dep_element_name) == "waiting"
    key_b1 = cli.get_element_key(project, back_dep_element_name)
    assert key_b1 != "{:?<64}".format("")
    result = cli.run(project=project, args=["build", back_dep_element_name])
    result.assert_success()
    assert cli.get_element_state(project, element_name) == "cached"
    key_a2 = cli.get_element_key(project, element_name)
    assert key_a2 != "{:?<64}".format("")
    assert cli.get_element_state(project, back_dep_element_name) == "cached"
    key_b2 = cli.get_element_key(project, back_dep_element_name)
    assert key_b2 != "{:?<64}".format("")
    result = cli.run(project=project, args=["build", back_dep_element_name])
    result.assert_success()

    # workspace keys are not recalculated
    assert key_a1 == key_a2
    assert key_b1 == key_b2

    # Checkout the result
    result = cli.run(project=project, args=["artifact", "checkout", back_dep_element_name, "--directory", checkout])
    result.assert_success()

    # Check that the pony.conf from the modified workspace exists
    filename = os.path.join(checkout, "etc", "pony.conf")
    assert os.path.exists(filename)

    # Check that the original /usr/bin/hello is not in the checkout
    assert not os.path.exists(os.path.join(checkout, "usr", "bin", "hello"))


@pytest.mark.datafiles(DATA_DIR)
def test_multiple_failed_builds(cli, tmpdir, datafiles):
    element_config = {"kind": "manual", "config": {"configure-commands": ["unknown_command_that_will_fail"]}}
    element_name, project, _ = open_workspace(cli, tmpdir, datafiles, "git", element_attrs=element_config)

    for _ in range(2):
        result = cli.run(project=project, args=["build", element_name])
        assert "BUG" not in result.stderr
        assert cli.get_element_state(project, element_name) != "cached"


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("subdir", [True, False], ids=["subdir", "no-subdir"])
@pytest.mark.parametrize("guess_element", [True, False], ids=["guess", "no-guess"])
def test_external_fetch(cli, datafiles, tmpdir_factory, subdir, guess_element):
    # An element with an open workspace can't be fetched, but we still expect fetches
    # to fetch any dependencies
    tmpdir = tmpdir_factory.mktemp(BASE_FILENAME)
    depend_element = "fetchable.bst"

    # Create an element to fetch (local sources do not need to fetch)
    create_element_size(depend_element, str(datafiles), "elements", [], 1024)

    element_name, project, workspace = open_workspace(
        cli, tmpdir, datafiles, "git", no_checkout=True, element_attrs={"depends": [depend_element]}
    )
    arg_elm = [element_name] if not guess_element else []

    if subdir:
        call_dir = os.path.join(workspace, "usr")
        os.makedirs(call_dir, exist_ok=True)
    else:
        call_dir = workspace

    # Assert that the depended element is not fetched yet
    assert cli.get_element_state(str(datafiles), depend_element) == "fetch needed"

    # Fetch the workspaced element
    result = cli.run(project=project, args=["-C", call_dir, "source", "fetch", *arg_elm])
    result.assert_success()

    # Assert that the depended element has now been fetched
    assert cli.get_element_state(str(datafiles), depend_element) == "buildable"


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("guess_element", [True, False], ids=["guess", "no-guess"])
def test_external_push_pull(cli, datafiles, tmpdir_factory, guess_element):
    # Pushing and pulling to/from an artifact cache works from an external workspace
    tmpdir = tmpdir_factory.mktemp(BASE_FILENAME)
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, "git")
    arg_elm = [element_name] if not guess_element else []

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:
        result = cli.run(project=project, args=["-C", workspace, "build", element_name])
        result.assert_success()

        cli.configure({"artifacts": {"url": share.repo, "push": True}})

        result = cli.run(project=project, args=["-C", workspace, "artifact", "push", *arg_elm])
        result.assert_success()

        result = cli.run(project=project, args=["-C", workspace, "artifact", "pull", "--deps", "all", *arg_elm])
        result.assert_success()


# Attempting to track in an open workspace is not a sensible thing and it's not compatible with workspaces as plugin
# sources: The new ref (if it differed from the old) would have been ignored regardless.
# The user should be expected to simply close the workspace before tracking.
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("guess_element", [True, False], ids=["guess", "no-guess"])
def test_external_track(cli, datafiles, tmpdir_factory, guess_element):
    tmpdir = tmpdir_factory.mktemp(BASE_FILENAME)
    element_name, project, workspace = open_workspace(cli, tmpdir, datafiles, "git")
    element_file = os.path.join(str(datafiles), "elements", element_name)
    arg_elm = [element_name] if not guess_element else []

    # Delete the ref from the source so that we can detect if the
    # element has been tracked after closing the workspace
    element_contents = _yaml.load(element_file, shortname=None)
    ref1 = element_contents.get_sequence("sources").mapping_at(0).get_str("ref")
    del element_contents.get_sequence("sources").mapping_at(0)["ref"]
    _yaml.roundtrip_dump(element_contents, element_file)

    result = cli.run(project=project, args=["-C", workspace, "source", "track", *arg_elm])
    result.assert_success()

    # Element is not tracked now
    element_contents = _yaml.load(element_file, shortname=None)
    assert "ref" not in element_contents.get_sequence("sources").mapping_at(0)

    # close the workspace
    result = cli.run(project=project, args=["-C", workspace, "workspace", "close", *arg_elm])
    result.assert_success()

    # and retrack the element
    result = cli.run(project=project, args=["source", "track", element_name])
    result.assert_success()

    element_contents = _yaml.load(element_file, shortname=None)
    ref2 = element_contents.get_sequence("sources").mapping_at(0).get_str("ref")
    # these values should be equivalent
    assert ref1 == ref2


@pytest.mark.datafiles(DATA_DIR)
def test_external_open_other(cli, datafiles, tmpdir_factory):
    # From inside an external workspace, open another workspace
    tmpdir1 = tmpdir_factory.mktemp(BASE_FILENAME)
    tmpdir2 = tmpdir_factory.mktemp(BASE_FILENAME)
    # Making use of the assumption that it's the same project in both invocations of open_workspace
    _, project, alpha_workspace = open_workspace(cli, tmpdir1, datafiles, "git", suffix="-alpha")
    beta_element, _, beta_workspace = open_workspace(cli, tmpdir2, datafiles, "git", suffix="-beta")

    # Closing the other element first, because I'm too lazy to create an
    # element without opening it
    result = cli.run(project=project, args=["workspace", "close", beta_element])
    result.assert_success()

    result = cli.run(
        project=project,
        args=["-C", alpha_workspace, "workspace", "open", "--force", "--directory", beta_workspace, beta_element],
    )
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
def test_external_reset_other(cli, datafiles, tmpdir_factory):
    tmpdir1 = tmpdir_factory.mktemp(BASE_FILENAME)
    tmpdir2 = tmpdir_factory.mktemp(BASE_FILENAME)
    # Making use of the assumption that it's the same project in both invocations of open_workspace
    _, project, alpha_workspace = open_workspace(cli, tmpdir1, datafiles, "git", suffix="-alpha")
    beta_element, _, _ = open_workspace(cli, tmpdir2, datafiles, "git", suffix="-beta")

    result = cli.run(project=project, args=["-C", alpha_workspace, "workspace", "reset", beta_element])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("guess_element", [True, False], ids=["guess", "no-guess"])
def test_external_reset_self(cli, datafiles, tmpdir, guess_element):
    element, project, workspace = open_workspace(cli, tmpdir, datafiles, "git")
    arg_elm = [element] if not guess_element else []

    # Command succeeds
    result = cli.run(project=project, args=["-C", workspace, "workspace", "reset", *arg_elm])
    result.assert_success()

    # Successive commands still work (i.e. .bstproject.yaml hasn't been deleted)
    result = cli.run(project=project, args=["-C", workspace, "workspace", "list"])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
def test_external_list(cli, datafiles, tmpdir_factory):
    tmpdir = tmpdir_factory.mktemp(BASE_FILENAME)
    # Making use of the assumption that it's the same project in both invocations of open_workspace
    _, project, workspace = open_workspace(cli, tmpdir, datafiles, "git")

    result = cli.run(project=project, args=["-C", workspace, "workspace", "list"])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
def test_multisource_workspace(cli, datafiles, tmpdir):
    # checks that if an element has multiple sources, then the opened workspace
    # will contain them
    project = str(datafiles)
    element_name = "multisource.bst"
    element = {
        "kind": "import",
        "sources": [{"kind": "local", "path": "files/bin-files"}, {"kind": "local", "path": "files/dev-files"}],
    }
    element_path = os.path.join(project, "elements", element_name)
    _yaml.roundtrip_dump(element, element_path)

    workspace_dir = os.path.join(str(tmpdir), "multisource")
    res = cli.run(project=project, args=["workspace", "open", "multisource.bst", "--directory", workspace_dir])
    res.assert_success()

    directories = os.listdir(os.path.join(workspace_dir, "usr"))
    assert "bin" in directories and "include" in directories


# This strange test tests against a regression raised in issue #919,
# where opening a workspace on a runtime dependency of a build only
# dependency causes `bst build` to not build the specified target
# but just successfully builds the workspaced element and happily
# exits without completing the build.
#
TEST_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)))


@pytest.mark.datafiles(TEST_DIR)
@pytest.mark.parametrize(
    ["case", "non_workspaced_elements_state"],
    [
        ("workspaced-build-dep", ["waiting", "waiting", "waiting", "waiting", "waiting"]),
        ("workspaced-runtime-dep", ["buildable", "buildable", "waiting", "waiting", "waiting"]),
    ],
)
@pytest.mark.parametrize("strict", [("strict"), ("non-strict")])
def test_build_all(cli, tmpdir, datafiles, case, strict, non_workspaced_elements_state):
    project = os.path.join(str(datafiles), case)
    workspace = os.path.join(str(tmpdir), "workspace")
    non_leaf_elements = ["elem2.bst", "elem3.bst", "stack.bst", "elem4.bst", "elem5.bst"]
    all_elements = ["elem1.bst", *non_leaf_elements]

    # Configure strict mode
    strict_mode = True
    if strict != "strict":
        strict_mode = False
    cli.configure({"projects": {"test": {"strict": strict_mode}}})

    # First open the workspace
    result = cli.run(project=project, args=["workspace", "open", "--directory", workspace, "elem1.bst"])
    result.assert_success()

    # Ensure all elements are waiting build the first
    assert cli.get_element_states(project, all_elements) == dict(
        zip(all_elements, ["buildable", *non_workspaced_elements_state])
    )

    # Now build the targets elem4.bst and elem5.bst
    result = cli.run(project=project, args=["build", "elem4.bst", "elem5.bst"])
    result.assert_success()

    # Assert that the target is built
    assert cli.get_element_states(project, all_elements) == {elem: "cached" for elem in all_elements}


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("strict", ["strict", "non-strict"])
def test_show_workspace_logs(cli, tmpdir, datafiles, strict):
    project = str(datafiles)
    workspace = os.path.join(str(tmpdir), "workspace")
    target = "manual.bst"

    # Configure strict mode
    strict_mode = True
    if strict != "strict":
        strict_mode = False
    cli.configure({"projects": {"test": {"strict": strict_mode}}})

    # First open the workspace
    result = cli.run(project=project, args=["workspace", "open", "--directory", workspace, target])
    result.assert_success()

    # Build the element
    result = cli.run(project=project, args=["build", target])
    result.assert_task_error(ErrorDomain.SANDBOX, "missing-command")

    result = cli.run(project=project, args=["artifact", "log", target])
    result.assert_success()

    # Assert that the log is not empty
    assert result.output != ""
