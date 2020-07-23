# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest
from buildstream.testing.runcli import cli  # pylint: disable=unused-import
from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream import _yaml
from buildstream.plugin import CoreWarnings
from tests.testutils import generate_junction

# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "overlaps")


def gen_project(project_dir, fail_on_overlap, use_fatal_warnings=True, project_name="test"):
    template = {"name": project_name, "min-version": "2.0"}
    if use_fatal_warnings:
        template["fatal-warnings"] = [CoreWarnings.OVERLAPS] if fail_on_overlap else []
    else:
        template["fail-on-overlap"] = fail_on_overlap
    projectfile = os.path.join(project_dir, "project.conf")
    _yaml.roundtrip_dump(template, projectfile)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("use_fatal_warnings", [True, False])
def test_overlaps(cli, datafiles, use_fatal_warnings):
    project_dir = str(datafiles)
    gen_project(project_dir, False, use_fatal_warnings)
    result = cli.run(project=project_dir, silent=True, args=["build", "collect.bst"])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("use_fatal_warnings", [True, False])
def test_overlaps_error(cli, datafiles, use_fatal_warnings):
    project_dir = str(datafiles)
    gen_project(project_dir, True, use_fatal_warnings)
    result = cli.run(project=project_dir, silent=True, args=["build", "collect.bst"])
    result.assert_main_error(ErrorDomain.STREAM, None)
    result.assert_task_error(ErrorDomain.PLUGIN, CoreWarnings.OVERLAPS)


@pytest.mark.datafiles(DATA_DIR)
def test_overlaps_whitelist(cli, datafiles):
    project_dir = str(datafiles)
    gen_project(project_dir, True)
    result = cli.run(project=project_dir, silent=True, args=["build", "collect-whitelisted.bst"])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
def test_overlaps_whitelist_ignored(cli, datafiles):
    project_dir = str(datafiles)
    gen_project(project_dir, False)
    result = cli.run(project=project_dir, silent=True, args=["build", "collect-whitelisted.bst"])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
def test_overlaps_whitelist_on_overlapper(cli, datafiles):
    # Tests that the overlapping element is responsible for whitelisting,
    # i.e. that if A overlaps B overlaps C, and the B->C overlap is permitted,
    # it'll still fail because A doesn't permit overlaps.
    project_dir = str(datafiles)
    gen_project(project_dir, True)
    result = cli.run(project=project_dir, silent=True, args=["build", "collect-partially-whitelisted.bst"])
    result.assert_main_error(ErrorDomain.STREAM, None)
    result.assert_task_error(ErrorDomain.PLUGIN, CoreWarnings.OVERLAPS)


@pytest.mark.datafiles(DATA_DIR)
def test_overlaps_whitelist_undefined_variable(cli, datafiles):
    project_dir = str(datafiles)
    gen_project(project_dir, False)
    result = cli.run(project=project_dir, silent=True, args=["build", "whitelist-undefined.bst"])

    # Assert that we get the expected undefined variable error,
    # and that it has the provenance we expect from whitelist-undefined.bst
    #
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.UNRESOLVED_VARIABLE)
    assert "whitelist-undefined.bst [line 13 column 6]" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("use_fatal_warnings", [True, False])
def test_overlaps_script(cli, datafiles, use_fatal_warnings):
    # Test overlaps with script element to test
    # Element.stage_dependency_artifacts() with Scope.RUN
    project_dir = str(datafiles)
    gen_project(project_dir, False, use_fatal_warnings)
    result = cli.run(project=project_dir, silent=True, args=["build", "script.bst"])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("project_policy", [("fail"), ("warn")])
@pytest.mark.parametrize("subproject_policy", [("fail"), ("warn")])
def test_overlap_subproject(cli, tmpdir, datafiles, project_policy, subproject_policy):
    project_dir = str(datafiles)
    subproject_dir = os.path.join(project_dir, "sub-project")
    junction_path = os.path.join(project_dir, "sub-project.bst")

    gen_project(project_dir, bool(project_policy == "fail"), project_name="test")
    gen_project(subproject_dir, bool(subproject_policy == "fail"), project_name="subtest")
    generate_junction(tmpdir, subproject_dir, junction_path)

    # Here we have a dependency chain where the project element
    # always overlaps with the subproject element.
    #
    # Test that overlap error vs warning policy for this overlap
    # is always controlled by the project and not the subproject.
    #
    result = cli.run(project=project_dir, silent=True, args=["build", "sub-collect.bst"])
    if project_policy == "fail":
        result.assert_main_error(ErrorDomain.STREAM, None)
        result.assert_task_error(ErrorDomain.PLUGIN, CoreWarnings.OVERLAPS)
    else:
        result.assert_success()
        assert "WARNING [overlaps]" in result.stderr
