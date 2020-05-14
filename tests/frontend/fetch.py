# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream.testing import generate_project
from buildstream import _yaml
from buildstream.exceptions import ErrorDomain, LoadErrorReason

from tests.testutils import generate_junction

from . import configure_project

# Project directory
TOP_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TOP_DIR, "project")


# Test all possible choices of the `--deps` option.
#
# NOTE: Elements used in this test must have sources that are not already
#       cached. The kind of the sources do not matter so long as they need to
#       be fetched from somewhere.
#       Currently we use remote sources for this purpose.
#
@pytest.mark.datafiles(os.path.join(TOP_DIR, "source-fetch"))
@pytest.mark.parametrize(
    "deps, expected_states",
    [
        ("build", ("fetch needed", "buildable", "fetch needed")),
        ("none", ("waiting", "fetch needed", "fetch needed")),
        ("run", ("waiting", "fetch needed", "buildable")),
        ("all", ("waiting", "buildable", "buildable")),
    ],
)
def test_fetch_deps(cli, datafiles, deps, expected_states):
    project = str(datafiles)
    generate_project(project)
    generate_project(project, {"aliases": {"project-root": "file:///" + project}})

    target = "bananas.bst"
    build_dep = "apples.bst"
    runtime_dep = "oranges.bst"

    # Assert that none of the sources are cached
    states = cli.get_element_states(project, [target, build_dep, runtime_dep])
    assert all([state == "fetch needed" for state in states.values()])

    # Now fetch the specified sources
    result = cli.run(project=project, args=["source", "fetch", "--deps", deps, target])
    result.assert_success()

    # Finally assert that we have fetched _only_ the desired sources
    states = cli.get_element_states(project, [target, build_dep, runtime_dep])
    states_flattened = (states[target], states[build_dep], states[runtime_dep])
    assert states_flattened == expected_states


@pytest.mark.datafiles(os.path.join(TOP_DIR, "consistencyerror"))
def test_fetch_consistency_error(cli, datafiles):
    project = str(datafiles)

    # When the error occurs outside of the scheduler at load time,
    # then the SourceError is reported directly as the main error.
    result = cli.run(project=project, args=["source", "fetch", "error.bst"])
    result.assert_main_error(ErrorDomain.SOURCE, "the-consistency-error")


@pytest.mark.datafiles(os.path.join(TOP_DIR, "consistencyerror"))
def test_fetch_consistency_bug(cli, datafiles):
    project = str(datafiles)

    result = cli.run(project=project, args=["source", "fetch", "bug.bst"])
    result.assert_main_error(ErrorDomain.PLUGIN, "source-bug")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("strict", [True, False], ids=["strict", "no-strict"])
@pytest.mark.parametrize("ref_storage", [("inline"), ("project.refs")])
def test_unfetched_junction(cli, tmpdir, datafiles, strict, ref_storage):
    project = str(datafiles)
    subproject_path = os.path.join(project, "files", "sub-project")
    junction_path = os.path.join(project, "elements", "junction.bst")
    element_path = os.path.join(project, "elements", "junction-dep.bst")

    configure_project(project, {"ref-storage": ref_storage})
    cli.configure({"projects": {"test": {"strict": strict}}})

    # Create a repo to hold the subproject and generate a junction element for it
    ref = generate_junction(tmpdir, subproject_path, junction_path, store_ref=(ref_storage == "inline"))

    # Create a stack element to depend on a cross junction element
    #
    element = {"kind": "stack", "depends": [{"junction": "junction.bst", "filename": "import-etc.bst"}]}
    _yaml.roundtrip_dump(element, element_path)

    # Dump a project.refs if we're using project.refs storage
    #
    if ref_storage == "project.refs":
        project_refs = {"projects": {"test": {"junction.bst": [{"ref": ref}]}}}
        _yaml.roundtrip_dump(project_refs, os.path.join(project, "junction.refs"))

    # Now try to fetch it, this should automatically result in fetching
    # the junction itself.
    result = cli.run(project=project, args=["source", "fetch", "junction-dep.bst"])
    result.assert_success()


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

    # Now try to fetch it, this will bail with the appropriate error
    # informing the user to track the junction first
    result = cli.run(project=project, args=["source", "fetch", "junction-dep.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.SUBPROJECT_INCONSISTENT)

    # Assert that we have the expected provenance encoded into the error
    element_node = _yaml.load(element_path, shortname="junction-dep.bst")
    ref_node = element_node.get_sequence("depends").mapping_at(0)
    provenance = ref_node.get_provenance()
    assert str(provenance) in result.stderr
