# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream import _yaml
from buildstream.exceptions import ErrorDomain, LoadErrorReason

from tests.testutils import generate_junction

# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "project"))
def test_show_progress_tally(cli, datafiles):
    # Check that the progress reporting messages give correct tallies
    project = str(datafiles)
    result = cli.run(project=project, args=["show", "compose-all.bst"])
    result.assert_success()
    assert "  3 subtasks processed" in result.stderr
    assert "3 of 3 subtasks processed" in result.stderr


@pytest.mark.datafiles(os.path.join(DATA_DIR, "project"))
def test_junction_tally(cli, tmpdir, datafiles):
    # Check that the progress reporting messages count elements in junctions
    project = str(datafiles)
    subproject_path = os.path.join(project, "files", "sub-project")
    junction_path = os.path.join(project, "elements", "junction.bst")
    element_path = os.path.join(project, "elements", "junction-dep.bst")

    # Create a repo to hold the subproject and generate a junction element for it
    generate_junction(tmpdir, subproject_path, junction_path, store_ref=True)

    # Create a stack element to depend on a cross junction element
    #
    element = {"kind": "stack", "depends": [{"junction": "junction.bst", "filename": "import-etc.bst"}]}
    _yaml.roundtrip_dump(element, element_path)

    result = cli.run(project=project, silent=True, args=["source", "fetch", "junction.bst"])
    result.assert_success()

    # Assert the correct progress tallies are in the logging
    result = cli.run(project=project, args=["show", "junction-dep.bst"])
    assert "  2 subtasks processed" in result.stderr
    assert "2 of 2 subtasks processed" in result.stderr


@pytest.mark.datafiles(os.path.join(DATA_DIR, "project"))
def test_nested_junction_tally(cli, tmpdir, datafiles):
    # Check that the progress reporting messages count elements in
    # junctions of junctions
    project = str(datafiles)
    sub1_path = os.path.join(project, "files", "sub-project")
    sub2_path = os.path.join(project, "files", "sub2-project")
    # A junction element which pulls sub1 into sub2
    sub1_element = os.path.join(project, "files", "sub2-project", "elements", "sub-junction.bst")
    # A junction element which pulls sub2 into the main project
    sub2_element = os.path.join(project, "elements", "junction.bst")
    element_path = os.path.join(project, "elements", "junction-dep.bst")

    generate_junction(tmpdir / "sub-project", sub1_path, sub1_element, store_ref=True)
    generate_junction(tmpdir / "sub2-project", sub2_path, sub2_element, store_ref=True)

    # Create a stack element to depend on a cross junction element
    #
    element = {"kind": "stack", "depends": [{"junction": "junction.bst", "filename": "import-sub.bst"}]}
    _yaml.roundtrip_dump(element, element_path)

    result = cli.run(project=project, silent=True, args=["source", "fetch", "junction.bst"])
    result.assert_success()

    # Assert the correct progress tallies are in the logging
    result = cli.run(project=project, args=["show", "junction-dep.bst"])
    assert "  3 subtasks processed" in result.stderr
    assert "3 of 3 subtasks processed" in result.stderr


@pytest.mark.datafiles(os.path.join(DATA_DIR, "project"))
def test_junction_dep_tally(cli, tmpdir, datafiles):
    # Check that the progress reporting messages count elements in junctions
    project = str(datafiles)
    subproject_path = os.path.join(project, "files", "sub-project")
    junction_path = os.path.join(project, "elements", "junction.bst")
    element_path = os.path.join(project, "elements", "junction-dep.bst")

    # Create a repo to hold the subproject and generate a junction element for it
    generate_junction(tmpdir, subproject_path, junction_path, store_ref=True)

    # Add dependencies to the junction (not allowed, but let's do it
    # anyway)
    with open(junction_path, "a") as f:
        deps = {"depends": ["manual.bst"]}
        _yaml.roundtrip_dump(deps, f)

    # Create a stack element to depend on a cross junction element
    #
    element = {"kind": "stack", "depends": [{"junction": "junction.bst", "filename": "import-etc.bst"}]}
    _yaml.roundtrip_dump(element, element_path)

    result = cli.run(project=project, silent=True, args=["source", "fetch", "junction-dep.bst"])

    # Since we aren't allowed to specify any dependencies on a
    # junction, we should fail
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_JUNCTION)

    # We don't get a final tally in this case
    assert "subtasks processed" not in result.stderr
