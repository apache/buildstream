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
import pytest
from buildstream._testing.runcli import cli  # pylint: disable=unused-import
from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream import _yaml
from buildstream import CoreWarnings, OverlapAction
from tests.testutils import generate_junction

# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "overlaps")


def gen_project(project_dir, fatal_warnings, *, project_name="test", use_plugin=False):
    template = {"name": project_name, "min-version": "2.0"}
    template["fatal-warnings"] = [CoreWarnings.OVERLAPS, CoreWarnings.UNSTAGED_FILES] if fatal_warnings else []
    if use_plugin:
        template["plugins"] = [{"origin": "local", "path": "plugins", "elements": ["overlap"]}]
    projectfile = os.path.join(project_dir, "project.conf")
    _yaml.roundtrip_dump(template, projectfile)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("error", [False, True], ids=["warning", "error"])
def test_unstaged_files(cli, datafiles, error):
    project_dir = str(datafiles)
    gen_project(project_dir, error)
    result = cli.run(project=project_dir, silent=True, args=["build", "unstaged.bst"])
    if error:
        result.assert_main_error(ErrorDomain.STREAM, None)
        result.assert_task_error(ErrorDomain.PLUGIN, CoreWarnings.UNSTAGED_FILES)
    else:
        result.assert_success()
        assert "WARNING [unstaged-files]" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("error", [False, True], ids=["warning", "error"])
def test_overlaps(cli, datafiles, error):
    project_dir = str(datafiles)
    gen_project(project_dir, error)
    result = cli.run(project=project_dir, silent=True, args=["build", "collect.bst"])
    if error:
        result.assert_main_error(ErrorDomain.STREAM, None)
        result.assert_task_error(ErrorDomain.PLUGIN, CoreWarnings.OVERLAPS)
    else:
        result.assert_success()
        assert "WARNING [overlaps]" in result.stderr


#
# When the overlap is whitelisted, there is no warning or error.
#
# Still test this in fatal/nonfatal warning modes
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("error", [False, True], ids=["warning", "error"])
def test_overlaps_whitelisted(cli, datafiles, error):
    project_dir = str(datafiles)
    gen_project(project_dir, error)
    result = cli.run(project=project_dir, silent=True, args=["build", "collect-whitelisted.bst"])
    result.assert_success()
    assert "WARNING [overlaps]" not in result.stderr


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("error", [False, True], ids=["warning", "error"])
def test_overlaps_whitelist_on_overlapper(cli, datafiles, error):
    # Tests that the overlapping element is responsible for whitelisting,
    # i.e. that if A overlaps B overlaps C, and the B->C overlap is permitted,
    # it'll still fail because A doesn't permit overlaps.
    project_dir = str(datafiles)
    gen_project(project_dir, error)
    result = cli.run(project=project_dir, silent=True, args=["build", "collect-partially-whitelisted.bst"])
    if error:
        result.assert_main_error(ErrorDomain.STREAM, None)
        result.assert_task_error(ErrorDomain.PLUGIN, CoreWarnings.OVERLAPS)
    else:
        result.assert_success()
        assert "WARNING [overlaps]" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_overlaps_whitelist_undefined_variable(cli, datafiles):
    project_dir = str(datafiles)
    gen_project(project_dir, False)
    result = cli.run(project=project_dir, silent=True, args=["show", "whitelist-undefined.bst"])

    # Assert that we get the expected undefined variable error,
    # and that it has the provenance we expect from whitelist-undefined.bst
    #
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.UNRESOLVED_VARIABLE)
    assert "whitelist-undefined.bst [line 13 column 6]" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_overlaps_script(cli, datafiles):
    # Test overlaps with script element to test
    # Element.stage_dependency_artifacts() with Scope.RUN
    project_dir = str(datafiles)
    gen_project(project_dir, False)
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


# Test unstaged-files warnings when staging to an alternative location than "/"
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("error", [False, True], ids=["warning", "error"])
def test_unstaged_files_relocated(cli, datafiles, error):
    project_dir = str(datafiles)
    gen_project(project_dir, error, use_plugin=True)
    result = cli.run(project=project_dir, silent=True, args=["build", "relocated-unstaged.bst"])
    if error:
        result.assert_main_error(ErrorDomain.STREAM, None)
        result.assert_task_error(ErrorDomain.PLUGIN, CoreWarnings.UNSTAGED_FILES)
    else:
        result.assert_success()
        assert "WARNING [unstaged-files]" in result.stderr


# Test overlap warnings when staging to an alternative location than "/"
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("error", [False, True], ids=["warning", "error"])
def test_overlaps_relocated(cli, datafiles, error):
    project_dir = str(datafiles)
    gen_project(project_dir, error, use_plugin=True)
    result = cli.run(project=project_dir, silent=True, args=["build", "relocated.bst"])
    if error:
        result.assert_main_error(ErrorDomain.STREAM, None)
        result.assert_task_error(ErrorDomain.PLUGIN, CoreWarnings.OVERLAPS)
    else:
        result.assert_success()
        assert "WARNING [overlaps]" in result.stderr


# Test overlap warnings as a result of multiple calls to Element.stage_dependency_artifacts()
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target,action,error",
    [
        ("multistage-overlap-ignore.bst", OverlapAction.IGNORE, False),
        ("multistage-overlap.bst", OverlapAction.WARNING, False),
        ("multistage-overlap.bst", OverlapAction.WARNING, True),
        ("multistage-overlap-error.bst", OverlapAction.ERROR, True),
    ],
    ids=["ignore", "warn-warning", "warn-error", "error"],
)
def test_overlaps_multistage(cli, datafiles, target, action, error):
    project_dir = str(datafiles)
    gen_project(project_dir, error, use_plugin=True)
    result = cli.run(project=project_dir, silent=True, args=["build", target])

    if action == OverlapAction.WARNING:
        if error:
            result.assert_main_error(ErrorDomain.STREAM, None)
            result.assert_task_error(ErrorDomain.PLUGIN, CoreWarnings.OVERLAPS)
        else:
            result.assert_success()
            assert "WARNING [overlaps]" in result.stderr
    elif action == OverlapAction.IGNORE:
        result.assert_success()
        assert "WARNING [overlaps]" not in result.stderr
    elif action == OverlapAction.ERROR:
        result.assert_main_error(ErrorDomain.STREAM, None)
        result.assert_task_error(ErrorDomain.ELEMENT, "overlaps")
