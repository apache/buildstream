# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream import _yaml
from buildstream.exceptions import ErrorDomain, LoadErrorReason

from tests.testutils import generate_junction

from . import configure_project

# Project directory
TOP_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TOP_DIR, "project")


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
