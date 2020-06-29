# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import itertools
import os
import stat

import pytest

from buildstream.testing import create_repo
from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream import _yaml
from tests.testutils import generate_junction
from . import configure_project

# Project directory
TOP_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TOP_DIR, "project")


def generate_element(repo, element_path, dependencies=None, ref=None):
    element = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
    if dependencies:
        element["depends"] = dependencies

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
    generate_element(repo, os.path.join(element_path, element_target_name), dependencies=[element_dep_name])

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


# Test various combinations of `--except` with all possible values for `--deps`
@pytest.mark.datafiles(os.path.join(DATA_DIR))
@pytest.mark.parametrize("ref_storage", [("inline"), ("project.refs")])
@pytest.mark.parametrize(
    "track_targets,deps,exceptions,tracked",
    [
        # --deps none
        ### Test with no exceptions
        (["0.bst"], "none", [], ["0.bst"]),
        (["3.bst"], "none", [], ["3.bst"]),
        (["2.bst", "3.bst"], "none", [], ["2.bst", "3.bst"]),
        ### Test excepting '2.bst'
        (["0.bst"], "none", ["2.bst"], ["0.bst"]),
        (["2.bst", "3.bst"], "none", ["2.bst"], ["3.bst"]),
        (["0.bst", "3.bst"], "none", ["2.bst"], ["0.bst", "3.bst"]),
        ### Test excepting '2.bst' and '3.bst'
        (["0.bst"], "none", ["2.bst", "3.bst"], ["0.bst"]),
        (["3.bst"], "none", ["2.bst", "3.bst"], []),
        (["2.bst", "3.bst"], "none", ["2.bst", "3.bst"], []),
        #
        # --deps all
        ### Test with no exceptions
        (["0.bst"], "all", [], ["0.bst", "2.bst", "3.bst", "4.bst", "5.bst", "6.bst", "7.bst"]),
        (["3.bst"], "all", [], ["3.bst", "4.bst", "5.bst", "6.bst"]),
        (["2.bst", "3.bst"], "all", [], ["2.bst", "3.bst", "4.bst", "5.bst", "6.bst", "7.bst"]),
        ### Test excepting '2.bst'
        (["0.bst"], "all", ["2.bst"], ["0.bst", "3.bst", "4.bst", "5.bst", "6.bst"]),
        (["3.bst"], "all", ["2.bst"], []),
        (["2.bst", "3.bst"], "all", ["2.bst"], ["3.bst", "4.bst", "5.bst", "6.bst"]),
        ### Test excepting '2.bst' and '3.bst'
        (["0.bst"], "all", ["2.bst", "3.bst"], ["0.bst"]),
        (["3.bst"], "all", ["2.bst", "3.bst"], []),
        (["2.bst", "3.bst"], "all", ["2.bst", "3.bst"], []),
    ],
)
def test_track_except(cli, datafiles, tmpdir, ref_storage, track_targets, deps, exceptions, tracked):
    project = str(datafiles)
    dev_files_path = os.path.join(project, "files", "dev-files")
    elements_path = os.path.join(project, "elements")

    repo = create_repo("git", str(tmpdir))
    ref = repo.create(dev_files_path)

    configure_project(project, {"ref-storage": ref_storage})

    create_elements = {
        "0.bst": ["2.bst", "3.bst"],
        "2.bst": ["3.bst", "7.bst"],
        "3.bst": ["4.bst", "5.bst", "6.bst"],
        "4.bst": [],
        "5.bst": [],
        "6.bst": ["5.bst"],
        "7.bst": [],
    }

    initial_project_refs = {}
    for element, dependencies in create_elements.items():
        element_path = os.path.join(elements_path, element)

        # Test the element inconsistency resolution by ensuring that
        # only elements that aren't tracked have refs
        if element in set(tracked):
            # Elements which should not have a ref set
            #
            generate_element(repo, element_path, dependencies)
        elif ref_storage == "project.refs":
            # Store a ref in project.refs
            #
            generate_element(repo, element_path, dependencies)
            initial_project_refs[element] = [{"ref": ref}]
        else:
            # Store a ref in the element itself
            #
            generate_element(repo, element_path, dependencies, ref=ref)

    # Generate initial project.refs
    if ref_storage == "project.refs":
        project_refs = {"projects": {"test": initial_project_refs}}
        _yaml.roundtrip_dump(project_refs, os.path.join(project, "project.refs"))

    args = ["source", "track", "--deps", deps, *track_targets]
    args += itertools.chain.from_iterable(zip(itertools.repeat("--except"), exceptions))

    result = cli.run(project=project, silent=True, args=args)
    result.assert_success()

    # Assert that we tracked exactly the elements we expected to
    tracked_elements = result.get_tracked_elements()
    assert set(tracked_elements) == set(tracked)


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
    generate_element(repo, target_path, dependencies=["subproject.bst"])
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
    result.assert_main_error(ErrorDomain.STREAM, None)
    result.assert_task_error(ErrorDomain.SOURCE, "the-consistency-error")


@pytest.mark.datafiles(os.path.join(TOP_DIR, "consistencyerror"))
def test_track_consistency_bug(cli, datafiles):
    project = str(datafiles)

    # Track the element causing an unhandled exception
    result = cli.run(project=project, args=["source", "track", "bug.bst"])

    # We expect BuildStream to fail gracefully, with no recorded exception.
    result.assert_main_error(ErrorDomain.STREAM, None)


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
