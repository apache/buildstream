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

from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream._testing import cli  # pylint: disable=unused-import

DATA_DIR = os.path.dirname(os.path.realpath(__file__))


#
# Exercising some different ways of loading the dependencies
#
@pytest.mark.datafiles(DATA_DIR)
def test_two_files(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies1")

    elements = cli.get_pipeline(project, ["target.bst"])
    assert elements == ["firstdep.bst", "target.bst"]


@pytest.mark.datafiles(DATA_DIR)
def test_shared_dependency(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies1")

    elements = cli.get_pipeline(project, ["shareddeptarget.bst"])
    assert elements == ["firstdep.bst", "shareddep.bst", "shareddeptarget.bst"]


@pytest.mark.datafiles(DATA_DIR)
def test_dependency_dict(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies1")
    elements = cli.get_pipeline(project, ["target-depdict.bst"])
    assert elements == ["firstdep.bst", "target-depdict.bst"]


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_dependency_declaration(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies1")
    result = cli.run(project=project, args=["show", "invaliddep.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_dependency_type(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies1")
    result = cli.run(project=project, args=["show", "invaliddeptype.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_strict_dependency(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies1")
    result = cli.run(project=project, args=["show", "invalidstrict.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_non_strict_dependency(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies1")
    result = cli.run(project=project, args=["show", "invalidnonstrict.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_circular_dependency(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies1")
    result = cli.run(project=project, args=["show", "circulartarget.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.CIRCULAR_DEPENDENCY)


@pytest.mark.datafiles(DATA_DIR)
def test_build_dependency(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies1")

    elements = cli.get_pipeline(project, ["builddep.bst"], scope="run")
    assert elements == ["builddep.bst"]

    elements = cli.get_pipeline(project, ["builddep.bst"], scope="build")
    assert elements == ["firstdep.bst"]


@pytest.mark.datafiles(DATA_DIR)
def test_runtime_dependency(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies1")
    elements = cli.get_pipeline(project, ["runtimedep.bst"], scope="build")

    # FIXME: The empty line should probably never happen here when there are no results.
    assert elements == [""]
    elements = cli.get_pipeline(project, ["runtimedep.bst"], scope="run")
    assert elements == ["firstdep.bst", "runtimedep.bst"]


@pytest.mark.datafiles(DATA_DIR)
def test_all_dependency(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies1")

    elements = cli.get_pipeline(project, ["alldep.bst"], scope="build")
    assert elements == ["firstdep.bst"]

    elements = cli.get_pipeline(project, ["alldep.bst"], scope="run")
    assert elements == ["firstdep.bst", "alldep.bst"]


@pytest.mark.datafiles(DATA_DIR)
def test_list_build_dependency(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies1")

    # Check that the pipeline includes the build dependency
    deps = cli.get_pipeline(project, ["builddep-list.bst"], scope="build")
    assert "firstdep.bst" in deps


@pytest.mark.datafiles(DATA_DIR)
def test_list_runtime_dependency(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies1")

    # Check that the pipeline includes the runtime dependency
    deps = cli.get_pipeline(project, ["runtimedep-list.bst"], scope="run")
    assert "firstdep.bst" in deps


@pytest.mark.datafiles(DATA_DIR)
def test_list_dependencies_combined(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies1")

    # Check that runtime deps get combined
    rundeps = cli.get_pipeline(project, ["list-combine.bst"], scope="run")
    assert "firstdep.bst" not in rundeps
    assert "seconddep.bst" in rundeps
    assert "thirddep.bst" in rundeps

    # Check that build deps get combined
    builddeps = cli.get_pipeline(project, ["list-combine.bst"], scope="build")
    assert "firstdep.bst" in builddeps
    assert "seconddep.bst" not in builddeps
    assert "thirddep.bst" in builddeps


@pytest.mark.datafiles(DATA_DIR)
def test_list_overlap(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies1")

    # Check that dependencies get merged
    rundeps = cli.get_pipeline(project, ["list-overlap.bst"], scope="run")
    assert "firstdep.bst" in rundeps
    builddeps = cli.get_pipeline(project, ["list-overlap.bst"], scope="build")
    assert "firstdep.bst" in builddeps


#
# Testing the order of elements reported when iterating through
# Element.dependencies() with various scopes.
#
@pytest.mark.datafiles(DATA_DIR)
def test_scope_all(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies2")
    elements = ["target.bst"]

    element_list = cli.get_pipeline(project, elements, scope="all")

    assert element_list == [
        "build-build.bst",
        "run-build.bst",
        "build.bst",
        "dep-one.bst",
        "run.bst",
        "dep-two.bst",
        "target.bst",
    ]


@pytest.mark.datafiles(DATA_DIR)
def test_scope_run(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies2")
    elements = ["target.bst"]

    element_list = cli.get_pipeline(project, elements, scope="run")

    assert element_list == [
        "dep-one.bst",
        "run.bst",
        "dep-two.bst",
        "target.bst",
    ]


@pytest.mark.datafiles(DATA_DIR)
def test_scope_build(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies2")
    elements = ["target.bst"]

    element_list = cli.get_pipeline(project, elements, scope="build")

    assert element_list == ["dep-one.bst", "run.bst", "dep-two.bst"]


@pytest.mark.datafiles(DATA_DIR)
def test_scope_build_of_child(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies2")
    elements = ["target.bst"]

    element_list = cli.get_pipeline(project, elements, scope="build")

    # First pass, lets check dep-two
    element = element_list[2]

    # Pass two, let's look at these
    element_list = cli.get_pipeline(project, [element], scope="build")

    assert element_list == ["run-build.bst", "build.bst"]


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target",
    [
        "merge-separate-lists.bst",
        "merge-single-list.bst",
    ],
    ids=["separate-lists", "single-list"],
)
def test_merge(cli, datafiles, target):
    project = os.path.join(str(datafiles), "dependencies2")

    # Test both build and run scopes, showing that the two dependencies
    # have been merged and the run-build.bst is both a runtime and build
    # time dependency, and is not loaded twice into the build graph.
    #
    element_list = cli.get_pipeline(project, [target], scope="build")
    assert element_list == ["run-build.bst"]

    element_list = cli.get_pipeline(project, [target], scope="run")
    assert element_list == ["run-build.bst", target]


@pytest.mark.datafiles(DATA_DIR)
def test_config_unsupported(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies3")

    result = cli.run(project=project, args=["show", "unsupported.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DEPENDENCY_CONFIG)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target,number",
    [
        ("supported1.bst", 1),
        ("supported2.bst", 2),
    ],
    ids=["one", "two"],
)
def test_config_supported(cli, datafiles, target, number):
    project = os.path.join(str(datafiles), "dependencies3")

    result = cli.run(project=project, args=["show", target])
    result.assert_success()

    assert "TEST PLUGIN FOUND {} ENABLED DEPENDENCIES".format(number) in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_config_runtime_error(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies3")

    # Test that it is considered an error to specify `config` on runtime-only dependencies
    #
    result = cli.run(project=project, args=["show", "runtime-error.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target,number",
    [
        ("shorthand-config.bst", 2),
        ("shorthand-junction.bst", 2),
    ],
    ids=["config", "junction"],
)
def test_shorthand(cli, datafiles, target, number):
    project = os.path.join(str(datafiles), "dependencies3")

    result = cli.run(project=project, args=["show", target])
    result.assert_success()

    assert "TEST PLUGIN FOUND {} ENABLED DEPENDENCIES".format(number) in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_filenames(cli, datafiles):
    project = os.path.join(str(datafiles), "dependencies3")

    result = cli.run(project=project, args=["show", "invalid-filenames.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)

    # Assert expected provenance
    assert "invalid-filenames.bst [line 9 column 4]" in result.stderr
