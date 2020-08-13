# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import stat
import os
import pytest

from buildstream.testing import create_repo, generate_project
from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream import _yaml
from tests.testutils import generate_junction
from . import configure_project

# Project directory
TOP_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TOP_DIR, "project")


def generate_element(repo, element_path, dep_name=None):
    element = {"kind": "import", "sources": [repo.source_config()]}
    if dep_name:
        element["depends"] = [dep_name]

    _yaml.roundtrip_dump(element, element_path)


@pytest.mark.datafiles(DATA_DIR)
def test_track_single(cli, tmpdir, datafiles):
    project = str(datafiles)
    dev_files_path = os.path.join(project, "files", "dev-files")
    element_path = os.path.join(project, "elements")
    element_dep_name = "track-test-dep.bst"
    element_target_name = "track-test-target.bst"

    # Create our repo object of the given source type with
    # the dev files, and then collect the initial ref.
    #
    repo = create_repo("git", str(tmpdir))
    repo.create(dev_files_path)

    # Write out our test targets
    generate_element(repo, os.path.join(element_path, element_dep_name))
    generate_element(repo, os.path.join(element_path, element_target_name), dep_name=element_dep_name)

    # Assert that tracking is needed for both elements
    states = cli.get_element_states(project, [element_target_name])
    assert states == {
        element_dep_name: "no reference",
        element_target_name: "no reference",
    }

    # Now first try to track only one element
    result = cli.run(project=project, args=["source", "track", "--deps", "none", element_target_name])
    result.assert_success()

    # And now fetch it
    result = cli.run(project=project, args=["source", "fetch", "--deps", "none", element_target_name])
    result.assert_success()

    # Assert that the dependency is waiting and the target has still never been tracked
    states = cli.get_element_states(project, [element_target_name])
    assert states == {
        element_dep_name: "no reference",
        element_target_name: "waiting",
    }


@pytest.mark.datafiles(os.path.join(TOP_DIR))
@pytest.mark.parametrize("ref_storage", [("inline"), ("project-refs")])
def test_track_optional(cli, tmpdir, datafiles, ref_storage):
    project = os.path.join(datafiles.dirname, datafiles.basename, "track-optional-" + ref_storage)
    dev_files_path = os.path.join(project, "files")
    element_path = os.path.join(project, "target.bst")

    # Create our repo object of the given source type with
    # the dev files, and then collect the initial ref.
    #
    repo = create_repo("git", str(tmpdir))
    repo.create(dev_files_path)

    # Now create an optional test branch and add a commit to that,
    # so two branches with different heads now exist.
    #
    repo.branch("test")
    repo.add_commit()

    # Substitute the {repo} for the git repo we created
    with open(element_path) as f:
        target_bst = f.read()
    target_bst = target_bst.format(repo=repo.repo)
    with open(element_path, "w") as f:
        f.write(target_bst)

    # First track for both options
    #
    # We want to track and persist the ref separately in this test
    #
    result = cli.run(project=project, args=["--option", "test", "False", "source", "track", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["--option", "test", "True", "source", "track", "target.bst"])
    result.assert_success()

    # Now fetch the key for both options
    #
    result = cli.run(
        project=project,
        args=["--option", "test", "False", "show", "--deps", "none", "--format", "%{key}", "target.bst"],
    )
    result.assert_success()
    master_key = result.output

    result = cli.run(
        project=project,
        args=["--option", "test", "True", "show", "--deps", "none", "--format", "%{key}", "target.bst"],
    )
    result.assert_success()
    test_key = result.output

    # Assert that the keys are different when having
    # tracked separate branches
    assert test_key != master_key


# Test all possible choices of the `--deps` option.
#
# NOTE: Elements used in this test must have sources that are trackable and do
#       not have a reference already. The kinds of the sources do not matter so
#       long as they can be tracked from somewhere.
#       Currently we use remote sources for this purpose.
#
@pytest.mark.datafiles(os.path.join(TOP_DIR, "source-track"))
@pytest.mark.parametrize(
    "deps, expected_states",
    [
        ("build", ("no reference", "buildable", "no reference")),
        ("none", ("waiting", "no reference", "no reference")),
        ("run", ("waiting", "no reference", "buildable")),
        ("all", ("waiting", "buildable", "buildable")),
    ],
)
def test_track_deps(cli, datafiles, deps, expected_states):
    project = str(datafiles)
    generate_project(project, {"aliases": {"project-root": "file:///" + project}})

    target = "bananas.bst"
    build_dep = "apples.bst"
    runtime_dep = "oranges.bst"

    # Assert that none of the sources have a reference
    states = cli.get_element_states(project, [target, build_dep, runtime_dep])
    assert all([state == "no reference" for state in states.values()])

    # Now track the specified sources
    result = cli.run(project=project, args=["source", "track", "--deps", deps, target])
    result.assert_success()

    # Finally assert that we have tracked _only_ the desired sources
    states = cli.get_element_states(project, [target, build_dep, runtime_dep])
    states_flattened = (states[target], states[build_dep], states[runtime_dep])
    assert states_flattened == expected_states


@pytest.mark.datafiles(os.path.join(TOP_DIR, "track-cross-junction"))
@pytest.mark.parametrize("cross_junction", [("cross"), ("nocross")])
@pytest.mark.parametrize("ref_storage", [("inline"), ("project.refs")])
def test_track_cross_junction(cli, tmpdir, datafiles, cross_junction, ref_storage):
    project = str(datafiles)
    dev_files_path = os.path.join(project, "files")
    target_path = os.path.join(project, "target.bst")
    subtarget_path = os.path.join(project, "subproject", "subtarget.bst")

    # Create our repo object of the given source type with
    # the dev files, and then collect the initial ref.
    #
    repo = create_repo("git", str(tmpdir))
    repo.create(dev_files_path)

    # Generate two elements using the git source, one in
    # the main project and one in the subproject.
    generate_element(repo, target_path, dep_name="subproject.bst")
    generate_element(repo, subtarget_path)

    # Generate project.conf
    #
    project_conf = {"name": "test", "min-version": "2.0", "ref-storage": ref_storage}
    _yaml.roundtrip_dump(project_conf, os.path.join(project, "project.conf"))

    #
    # FIXME: This can be simplified when we have support
    #        for addressing of junctioned elements.
    #
    def get_subproject_element_state():
        result = cli.run(project=project, args=["show", "--deps", "all", "--format", "%{name}|%{state}", "target.bst"])
        result.assert_success()

        # Create two dimentional list of the result,
        # first line should be the junctioned element
        lines = [line.split("|") for line in result.output.splitlines()]
        assert lines[0][0] == "subproject-junction.bst:subtarget.bst"
        return lines[0][1]

    #
    # Assert that we have no reference yet for the cross junction element
    #
    assert get_subproject_element_state() == "no reference"

    # Track recursively across the junction
    args = ["source", "track", "--deps", "all"]
    if cross_junction == "cross":
        args += ["--cross-junctions"]
    args += ["target.bst"]

    result = cli.run(project=project, args=args)

    if ref_storage == "inline":

        if cross_junction == "cross":
            #
            # Cross junction tracking is not allowed when the toplevel project
            # is using inline ref storage.
            #
            result.assert_main_error(ErrorDomain.PIPELINE, "untrackable-sources")
        else:
            #
            # No cross juction tracking was requested
            #
            result.assert_success()
            assert get_subproject_element_state() == "no reference"
    else:
        #
        # Tracking is allowed with project.refs ref storage
        #
        result.assert_success()

        #
        # If cross junction tracking was enabled, we should now be buildable
        #
        if cross_junction == "cross":
            assert get_subproject_element_state() == "buildable"
        else:
            assert get_subproject_element_state() == "no reference"


@pytest.mark.datafiles(os.path.join(TOP_DIR, "consistencyerror"))
def test_track_consistency_error(cli, datafiles):
    project = str(datafiles)

    # Track the element causing a consistency error
    result = cli.run(project=project, args=["source", "track", "error.bst"])
    result.assert_main_error(ErrorDomain.SOURCE, "the-consistency-error")


@pytest.mark.datafiles(os.path.join(TOP_DIR, "consistencyerror"))
def test_track_consistency_bug(cli, datafiles):
    project = str(datafiles)

    # Track the element causing an unhandled exception
    result = cli.run(project=project, args=["source", "track", "bug.bst"])

    # We expect BuildStream to fail gracefully, with no recorded exception.
    result.assert_main_error(ErrorDomain.PLUGIN, "source-bug")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", [("inline"), ("project.refs")])
def test_inconsistent_junction(cli, tmpdir, datafiles, ref_storage):
    project = str(datafiles)
    subproject_path = os.path.join(project, "files", "sub-project")
    junction_path = os.path.join(project, "elements", "junction.bst")
    element_path = os.path.join(project, "elements", "junction-dep.bst")

    configure_project(project, {"ref-storage": ref_storage})

    # Create a repo to hold the subproject and generate a junction element for it
    generate_junction(tmpdir, subproject_path, junction_path, store_ref=False)

    # Create a stack element to depend on a cross junction element
    #
    element = {"kind": "stack", "depends": [{"junction": "junction.bst", "filename": "import-etc.bst"}]}
    _yaml.roundtrip_dump(element, element_path)

    # Now try to track it, this will bail with the appropriate error
    # informing the user to track the junction first
    result = cli.run(project=project, args=["source", "track", "junction-dep.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.SUBPROJECT_INCONSISTENT)

    # Assert that we have the expected provenance encoded into the error
    element_node = _yaml.load(element_path, shortname="junction-dep.bst")
    ref_node = element_node.get_sequence("depends").mapping_at(0)
    provenance = ref_node.get_provenance()
    assert str(provenance) in result.stderr


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", [("inline"), ("project.refs")])
def test_junction_element(cli, tmpdir, datafiles, ref_storage):
    project = str(datafiles)
    subproject_path = os.path.join(project, "files", "sub-project")
    junction_path = os.path.join(project, "elements", "junction.bst")
    element_path = os.path.join(project, "elements", "junction-dep.bst")

    configure_project(project, {"ref-storage": ref_storage})

    # Create a repo to hold the subproject and generate a junction element for it
    generate_junction(tmpdir, subproject_path, junction_path, store_ref=False)

    # Create a stack element to depend on a cross junction element
    #
    element = {"kind": "stack", "depends": [{"junction": "junction.bst", "filename": "import-etc.bst"}]}
    _yaml.roundtrip_dump(element, element_path)

    # First demonstrate that showing the pipeline yields an error
    result = cli.run(project=project, args=["show", "junction-dep.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.SUBPROJECT_INCONSISTENT)

    # Assert that we have the expected provenance encoded into the error
    element_node = _yaml.load(element_path, shortname="junction-dep.bst")
    ref_node = element_node.get_sequence("depends").mapping_at(0)
    provenance = ref_node.get_provenance()
    assert str(provenance) in result.stderr

    # Now track the junction itself
    result = cli.run(project=project, args=["source", "track", "junction.bst"])
    result.assert_success()

    # Now assert element state (via bst show under the hood) of the dep again
    assert cli.get_element_state(project, "junction-dep.bst") == "waiting"


@pytest.mark.datafiles(DATA_DIR)
def test_track_error_cannot_write_file(cli, tmpdir, datafiles):
    if os.geteuid() == 0:
        pytest.skip("This is not testable with root permissions")

    project = str(datafiles)
    dev_files_path = os.path.join(project, "files", "dev-files")
    element_path = os.path.join(project, "elements")
    element_name = "track-test.bst"

    configure_project(project, {"ref-storage": "inline"})

    repo = create_repo("git", str(tmpdir))
    repo.create(dev_files_path)

    element_full_path = os.path.join(element_path, element_name)
    generate_element(repo, element_full_path)

    st = os.stat(element_path)
    try:
        read_mask = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
        os.chmod(element_path, stat.S_IMODE(st.st_mode) & ~read_mask)

        result = cli.run(project=project, args=["source", "track", element_name])
        result.assert_main_error(ErrorDomain.STREAM, None)
        result.assert_task_error(ErrorDomain.SOURCE, "save-ref-error")
    finally:
        os.chmod(element_path, stat.S_IMODE(st.st_mode))


@pytest.mark.datafiles(DATA_DIR)
def test_no_needless_overwrite(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    dev_files_path = os.path.join(project, "files", "dev-files")
    element_path = os.path.join(project, "elements")
    target = "track-test-target.bst"

    # Create our repo object of the given source type with
    # the dev files, and then collect the initial ref.
    #
    repo = create_repo("git", str(tmpdir))
    repo.create(dev_files_path)

    # Write out our test target and assert it exists
    generate_element(repo, os.path.join(element_path, target))
    path_to_target = os.path.join(element_path, target)
    assert os.path.exists(path_to_target)
    creation_mtime = os.path.getmtime(path_to_target)

    # Assert tracking is needed
    states = cli.get_element_states(project, [target])
    assert states[target] == "no reference"

    # Perform the track
    result = cli.run(project=project, args=["source", "track", target])
    result.assert_success()

    track1_mtime = os.path.getmtime(path_to_target)

    assert creation_mtime != track1_mtime

    # Now (needlessly) track again
    result = cli.run(project=project, args=["source", "track", target])
    result.assert_success()

    track2_mtime = os.path.getmtime(path_to_target)

    assert track1_mtime == track2_mtime


# Regression test for https://gitlab.com/BuildStream/buildstream/-/issues/1265.
# Ensure that we can successfully track a `.bst` file that has comments inside
# one of our YAML directives (like list append, prepend etc).
@pytest.mark.datafiles(os.path.join(TOP_DIR, "source-track"))
def test_track_with_comments(cli, datafiles):
    project = str(datafiles)
    generate_project(project, {"aliases": {"project-root": "file:///" + project}})

    target = "comments.bst"

    # Assert that it needs to be tracked
    assert cli.get_element_state(project, target) == "no reference"

    # Track and fetch the sources
    result = cli.run(project=project, args=["source", "track", target])
    result.assert_success()
    result = cli.run(project=project, args=["source", "fetch", target])
    result.assert_success()

    # Assert that the sources are cached
    assert cli.get_element_state(project, target) == "buildable"
