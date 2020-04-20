# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os

import pytest

from buildstream import _yaml
from buildstream.testing import cli, create_repo  # pylint: disable=unused-import
from tests.testutils import create_artifact_share

# project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "default-target",)


###################################
#      build/show operations      #
###################################


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("operation,expected_state", [("show", "buildable"), ("build", "cached")])
def test_no_default(cli, datafiles, operation, expected_state):
    project = str(datafiles)
    all_targets = ["dummy_1.bst", "dummy_2.bst", "dummy_3.bst", "dummy_stack.bst"]

    result = cli.run(project=project, args=[operation])
    result.assert_success()

    states = cli.get_element_states(project, all_targets)
    assert all(states[e] == expected_state for e in all_targets)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("operation,expected_state", [("show", "buildable"), ("build", "cached")])
def test_default_target(cli, datafiles, operation, expected_state):
    project = str(datafiles)
    project_path = os.path.join(project, "project.conf")

    # First, modify project configuration to set a default target
    project_conf = {
        "name": "test-default-target",
        "min-version": "2.0",
        "element-path": "elements",
        "defaults": {"targets": ["dummy_stack.bst"]},
    }
    _yaml.roundtrip_dump(project_conf, project_path)

    # dummy_stack only depends on dummy_1 and dummy_2, but not dummy_3
    all_targets = ["dummy_1.bst", "dummy_2.bst", "dummy_stack.bst"]

    result = cli.run(project=project, args=[operation])
    result.assert_success()

    states = cli.get_element_states(project, all_targets)
    assert all(states[e] == expected_state for e in all_targets)

    # assert that dummy_3 isn't included in the output
    assert "dummy_3.bst" not in states


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("operation,expected_state", [("show", "buildable"), ("build", "cached")])
def test_no_default_with_junction(cli, datafiles, operation, expected_state):
    project = str(datafiles)
    junction_path = os.path.join(project, "elements", "junction.bst")
    target_path = os.path.join(project, "elements", "junction-target.bst")

    # First, create a junction element to refer to the subproject
    junction_config = {"kind": "junction", "sources": [{"kind": "local", "path": "files/sub-project",}]}
    _yaml.roundtrip_dump(junction_config, junction_path)

    # Then, create a stack element with dependency on cross junction element
    target_config = {"kind": "stack", "runtime-depends": ["junction.bst:dummy_subproject.bst"]}
    _yaml.roundtrip_dump(target_config, target_path)

    # Now try to perform the specified operation.
    # This should automatically fetch the junction at load time.
    result = cli.run(project=project, args=[operation])
    result.assert_success()

    assert cli.get_element_state(project, "junction.bst:dummy_subproject.bst") == expected_state
    assert cli.get_element_state(project, "junction-target.bst") == expected_state


###################################
#     track/fetch operations      #
###################################


@pytest.mark.datafiles(DATA_DIR)
def test_default_target_track(cli, tmpdir, datafiles):
    project = str(datafiles)
    project_path = os.path.join(project, "project.conf")
    target = "track-fetch-test.bst"

    # First, create an element with trackable sources
    repo = create_repo("git", str(tmpdir))
    repo.create(project)
    element_conf = {"kind": "import", "sources": [repo.source_config()]}
    _yaml.roundtrip_dump(element_conf, os.path.join(project, "elements", target))

    # Then, make it the default target
    project_conf = {
        "name": "test-default-target",
        "min-version": "2.0",
        "element-path": "elements",
        "defaults": {"targets": [target]},
    }
    _yaml.roundtrip_dump(project_conf, project_path)

    # Setup finished. Track it now
    assert cli.get_element_state(project, target) == "no reference"
    result = cli.run(project=project, args=["source", "track"])
    result.assert_success()
    # Tracking will result in fetching it automatically, so we expect the state
    # to be buildable.
    assert cli.get_element_state(project, target) == "buildable"


@pytest.mark.datafiles(DATA_DIR)
def test_default_target_fetch(cli, tmpdir, datafiles):
    project = str(datafiles)
    project_path = os.path.join(project, "project.conf")
    target = "track-fetch-test.bst"

    # First, create an element with trackable sources
    repo = create_repo("git", str(tmpdir))
    ref = repo.create(project)
    element_conf = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element_conf, os.path.join(project, "elements", target))

    # Then, make it the default target
    project_conf = {
        "name": "test-default-target",
        "min-version": "2.0",
        "element-path": "elements",
        "defaults": {"targets": [target]},
    }
    _yaml.roundtrip_dump(project_conf, project_path)

    # Setup finished. Track it now
    assert cli.get_element_state(project, target) == "fetch needed"
    result = cli.run(project=project, args=["source", "fetch"])
    result.assert_success()
    assert cli.get_element_state(project, target) == "buildable"


###################################
#      pull/push operations      #
###################################


@pytest.mark.datafiles(DATA_DIR)
def test_default_target_push_pull(cli, tmpdir, datafiles):
    project = str(datafiles)
    project_path = os.path.join(project, "project.conf")
    target = "dummy_1.bst"

    # Set a default target
    project_conf = {
        "name": "test-default-target",
        "min-version": "2.0",
        "element-path": "elements",
        "defaults": {"targets": [target]},
    }
    _yaml.roundtrip_dump(project_conf, project_path)

    # Build the target
    result = cli.run(project=project, args=["build"])
    result.assert_success()
    assert cli.get_element_state(project, target) == "cached"

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:
        # Push the artifacts
        cli.configure({"artifacts": {"url": share.repo, "push": True}})
        result = cli.run(project=project, args=["artifact", "push"])
        result.assert_success()

        # Delete local artifacts
        # Note that `artifact delete` does not support default targets
        result = cli.run(project=project, args=["artifact", "delete", target])
        result.assert_success()

        # Target should be buildable now, and we should be able to pull it
        assert cli.get_element_state(project, target) == "buildable"
        result = cli.run(project=project, args=["artifact", "pull"])
        assert cli.get_element_state(project, target) == "cached"
