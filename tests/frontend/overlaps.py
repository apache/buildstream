import os
import pytest
from tests.testutils.runcli import cli
from buildstream._exceptions import ErrorDomain
from buildstream import _yaml

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "overlaps"
)

project_template = {
    "name": "test",
    "element-path": "."
}


def gen_project(project_dir, fail_on_overlap):
    template = dict(project_template)
    template["fail-on-overlap"] = fail_on_overlap
    projectfile = os.path.join(project_dir, "project.conf")
    _yaml.dump(template, projectfile)


@pytest.mark.datafiles(DATA_DIR)
def test_overlaps(cli, datafiles):
    project_dir = str(datafiles)
    gen_project(project_dir, False)
    result = cli.run(project=project_dir, silent=True, args=[
        'build', 'collect.bst'])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
def test_overlaps_error(cli, datafiles):
    project_dir = str(datafiles)
    gen_project(project_dir, True)
    result = cli.run(project=project_dir, silent=True, args=[
        'build', 'collect.bst'])
    result.assert_main_error(ErrorDomain.STREAM, None)
    result.assert_task_error(ErrorDomain.ELEMENT, "overlap-error")


@pytest.mark.datafiles(DATA_DIR)
def test_overlaps_whitelist(cli, datafiles):
    project_dir = str(datafiles)
    gen_project(project_dir, True)
    result = cli.run(project=project_dir, silent=True, args=[
        'build', 'collect-whitelisted.bst'])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
def test_overlaps_whitelist_ignored(cli, datafiles):
    project_dir = str(datafiles)
    gen_project(project_dir, False)
    result = cli.run(project=project_dir, silent=True, args=[
        'build', 'collect-whitelisted.bst'])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
def test_overlaps_whitelist_on_overlapper(cli, datafiles):
    # Tests that the overlapping element is responsible for whitelisting,
    # i.e. that if A overlaps B overlaps C, and the B->C overlap is permitted,
    # it'll still fail because A doesn't permit overlaps.
    project_dir = str(datafiles)
    gen_project(project_dir, True)
    result = cli.run(project=project_dir, silent=True, args=[
        'build', 'collect-partially-whitelisted.bst'])
    result.assert_main_error(ErrorDomain.STREAM, None)
    result.assert_task_error(ErrorDomain.ELEMENT, "overlap-error")


@pytest.mark.datafiles(DATA_DIR)
def test_overlaps_script(cli, datafiles):
    # Test overlaps with script element to test
    # Element.stage_dependency_artifacts() with Scope.RUN
    project_dir = str(datafiles)
    gen_project(project_dir, False)
    result = cli.run(project=project_dir, silent=True, args=[
        'build', 'script.bst'])
    result.assert_success()
