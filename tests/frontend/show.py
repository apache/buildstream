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
import sys
import shutil
import pytest
from buildstream._testing import cli  # pylint: disable=unused-import
from buildstream import _yaml
from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream.types import CoreWarnings

from tests.testutils import generate_junction

from . import configure_project

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "project"))
@pytest.mark.parametrize(
    "target,fmt,expected",
    [
        ("import-bin.bst", "%{name}", "import-bin.bst"),
        ("import-bin.bst", "%{state}", "buildable"),
        ("compose-all.bst", "%{state}", "waiting"),
    ],
)
def test_show(cli, datafiles, target, fmt, expected):
    project = str(datafiles)
    result = cli.run(project=project, silent=True, args=["show", "--deps", "none", "--format", fmt, target])
    result.assert_success()

    if result.output.strip() != expected:
        raise AssertionError("Expected output:\n{}\nInstead received output:\n{}".format(expected, result.output))


@pytest.mark.datafiles(
    os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "invalid_element_path",
    )
)
def test_show_invalid_element_path(cli, datafiles):
    project = str(datafiles)
    cli.run(project=project, silent=True, args=["show", "foo.bst"])


@pytest.mark.datafiles(os.path.join(DATA_DIR, "project_fail"))
def test_show_fail(cli, datafiles):
    project = str(datafiles)
    result = cli.run(project=project, silent=True, args=["show"])

    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


# Test behaviors of user supplied glob patterns
@pytest.mark.datafiles(os.path.join(DATA_DIR, "simple"))
@pytest.mark.parametrize(
    "pattern,expected_elements",
    [
        # Only bst files, same as "**" for `bst show`
        #
        ("**.bst", ["import-bin.bst", "import-dev.bst", "compose-all.bst", "target.bst", "subdir/target.bst"]),
        # Use regular globbing without matching path separators, this should exclude
        # the target in the subdirectory.
        #
        ("*.bst", ["import-bin.bst", "import-dev.bst", "compose-all.bst", "target.bst"]),
        # Report only targets in the subdirectory
        #
        ("subdir/*.bst", ["subdir/target.bst"]),
        # Report both targets which end in "target.bst"
        #
        ("**target.bst", ["target.bst", "subdir/target.bst"]),
        # All elements starting with the prefix "import"
        #
        ("import*.bst", ["import-bin.bst", "import-dev.bst"]),
    ],
    ids=["**.bst", "*.bst", "subdir/*", "**target.bst", "import*"],
)
def test_show_glob(cli, tmpdir, datafiles, pattern, expected_elements):
    project = str(datafiles)

    result = cli.run(project=project, args=["show", "--deps", "none", "--format", "%{name}", pattern])
    result.assert_success()

    output = result.output.strip().splitlines()

    # Assert that the number of results match the number of expected results
    assert len(output) == len(expected_elements)

    # Assert that each expected result was found.
    for expected in expected_elements:
        assert expected in output, "Expected result {} not found".format(expected)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "project"))
@pytest.mark.parametrize(
    "target,except_,expected",
    [
        ("target.bst", "import-bin.bst", ["import-dev.bst", "compose-all.bst", "target.bst"]),
        ("target.bst", "import-dev.bst", ["import-bin.bst", "compose-all.bst", "target.bst"]),
        ("target.bst", "compose-all.bst", ["import-bin.bst", "target.bst"]),
        ("compose-all.bst", "import-bin.bst", ["import-dev.bst", "compose-all.bst"]),
    ],
)
def test_show_except_simple(cli, datafiles, target, except_, expected):
    project = str(datafiles)
    result = cli.run(
        project=project,
        silent=True,
        args=["show", "--deps", "all", "--format", "%{name}", "--except", except_, target],
    )

    result.assert_success()

    results = result.output.strip().splitlines()
    if results != expected:
        raise AssertionError("Expected elements:\n{}\nInstead received elements:\n{}".format(expected, results))


# This test checks various constructions of a pipeline
# with one or more targets and 0 or more exception elements,
# each data set provides the targets, exceptions and expected
# result list.
#
@pytest.mark.datafiles(os.path.join(DATA_DIR, "exceptions"))
@pytest.mark.parametrize(
    "targets,exceptions,expected",
    [
        # Test without exceptions, lets just see the whole list here
        (
            ["build.bst"],
            None,
            [
                "fourth-level-1.bst",
                "third-level-1.bst",
                "fourth-level-2.bst",
                "third-level-2.bst",
                "fourth-level-3.bst",
                "third-level-3.bst",
                "second-level-1.bst",
                "first-level-1.bst",
                "first-level-2.bst",
                "build.bst",
            ],
        ),
        # Test one target and excepting a part of the pipeline, this
        # removes forth-level-1 and third-level-1
        (
            ["build.bst"],
            ["third-level-1.bst"],
            [
                "fourth-level-2.bst",
                "third-level-2.bst",
                "fourth-level-3.bst",
                "third-level-3.bst",
                "second-level-1.bst",
                "first-level-1.bst",
                "first-level-2.bst",
                "build.bst",
            ],
        ),
        # Test one target and excepting a part of the pipeline, check that
        # excepted dependencies remain in the pipeline if depended on from
        # outside of the except element
        (
            ["build.bst"],
            ["second-level-1.bst"],
            [
                "fourth-level-2.bst",
                "third-level-2.bst",  # first-level-2 depends on this, so not excepted
                "first-level-1.bst",
                "first-level-2.bst",
                "build.bst",
            ],
        ),
        # The same as the above test, but excluding the toplevel build.bst,
        # instead only select the two toplevel dependencies as targets
        (
            ["first-level-1.bst", "first-level-2.bst"],
            ["second-level-1.bst"],
            [
                "fourth-level-2.bst",
                "third-level-2.bst",  # first-level-2 depends on this, so not excepted
                "first-level-1.bst",
                "first-level-2.bst",
            ],
        ),
        # Test one target and excepting an element outisde the pipeline
        (
            ["build.bst"],
            ["unrelated-1.bst"],
            [
                "fourth-level-2.bst",
                "third-level-2.bst",  # first-level-2 depends on this, so not excepted
                "first-level-1.bst",
                "first-level-2.bst",
                "build.bst",
            ],
        ),
        # Test one target and excepting two elements
        (
            ["build.bst"],
            ["unrelated-1.bst", "unrelated-2.bst"],
            [
                "first-level-1.bst",
                "build.bst",
            ],
        ),
    ],
)
def test_show_except(cli, datafiles, targets, exceptions, expected):
    basedir = str(datafiles)
    results = cli.get_pipeline(basedir, targets, except_=exceptions, scope="all")
    if results != expected:
        raise AssertionError("Expected elements:\n{}\nInstead received elements:\n{}".format(expected, results))


@pytest.mark.datafiles(os.path.join(DATA_DIR, "project"))
def test_target_is_dependency(cli, datafiles):
    project = str(datafiles)
    elements = ["multiple_targets/dependency/zebry.bst", "multiple_targets/dependency/horsey.bst"]

    args = ["show", "-d", "all", "-f", "%{name}", *elements]
    result = cli.run(project=project, args=args)

    result.assert_success()

    # Get the order
    names = result.output.splitlines()
    names = [name[len("multiple_targets/dependency/") :] for name in names]

    assert names == ["pony.bst", "horsey.bst", "zebry.bst"]


@pytest.mark.datafiles(os.path.join(DATA_DIR, "project"))
@pytest.mark.parametrize("ref_storage", [("inline"), ("project.refs")])
@pytest.mark.parametrize("element_name", ["junction-dep.bst", "junction.bst:import-etc.bst"])
@pytest.mark.parametrize("workspaced", [True, False], ids=["workspace", "no-workspace"])
def test_unfetched_junction(cli, tmpdir, datafiles, ref_storage, element_name, workspaced):
    project = str(datafiles)
    subproject_path = os.path.join(project, "files", "sub-project")
    junction_path = os.path.join(project, "elements", "junction.bst")
    element_path = os.path.join(project, "elements", "junction-dep.bst")

    configure_project(project, {"ref-storage": ref_storage})

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

    # Open a workspace if we're testing workspaced behavior
    if workspaced:
        result = cli.run(
            project=project,
            silent=True,
            args=["workspace", "open", "--no-checkout", "--directory", subproject_path, "junction.bst"],
        )
        result.assert_success()

    # Assert successful bst show (requires implicit subproject fetching)
    result = cli.run(project=project, silent=True, args=["show", element_name])
    result.assert_success()


@pytest.mark.datafiles(os.path.join(DATA_DIR, "project"))
@pytest.mark.parametrize("ref_storage", [("inline"), ("project.refs")])
@pytest.mark.parametrize("workspaced", [True, False], ids=["workspace", "no-workspace"])
def test_inconsistent_junction(cli, tmpdir, datafiles, ref_storage, workspaced):
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

    # Open a workspace if we're testing workspaced behavior
    if workspaced:
        result = cli.run(
            project=project,
            silent=True,
            args=["workspace", "open", "--no-checkout", "--directory", subproject_path, "junction.bst"],
        )
        result.assert_success()

    # Assert the correct error when trying to show the pipeline
    dep_result = cli.run(project=project, silent=True, args=["show", "junction-dep.bst"])

    # Assert the correct error when trying to show the pipeline
    etc_result = cli.run(project=project, silent=True, args=["show", "junction.bst:import-etc.bst"])

    # If a workspace is open, no ref is needed
    if workspaced:
        dep_result.assert_success()
        etc_result.assert_success()
    else:
        # Assert that we have the expected provenance encoded into the error
        element_node = _yaml.load(element_path, shortname="junction-dep.bst")
        ref_node = element_node.get_sequence("depends").mapping_at(0)
        provenance = ref_node.get_provenance()
        assert str(provenance) in dep_result.stderr

        dep_result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.SUBPROJECT_INCONSISTENT)
        etc_result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.SUBPROJECT_INCONSISTENT)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "project"))
@pytest.mark.parametrize("element_name", ["junction-dep.bst", "junction.bst:import-etc.bst"])
@pytest.mark.parametrize("workspaced", [True, False], ids=["workspace", "no-workspace"])
def test_fetched_junction(cli, tmpdir, datafiles, element_name, workspaced):
    project = str(datafiles)
    project = os.path.join(datafiles.dirname, datafiles.basename)
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

    # Open a workspace if we're testing workspaced behavior
    if workspaced:
        result = cli.run(
            project=project,
            silent=True,
            args=["workspace", "open", "--no-checkout", "--directory", subproject_path, "junction.bst"],
        )
        result.assert_success()

    # Assert the correct error when trying to show the pipeline
    result = cli.run(project=project, silent=True, args=["show", "--format", "%{name}-%{state}", element_name])

    results = result.output.strip().splitlines()
    assert "junction.bst:import-etc.bst-buildable" in results


###############################################################
#                   Testing recursion depth                   #
###############################################################
@pytest.mark.parametrize("dependency_depth", [100, 150, 1200])
def test_exceed_max_recursion_depth(cli, tmpdir, dependency_depth):
    project_name = "recursion-test"
    path = str(tmpdir)
    project_path = os.path.join(path, project_name)

    def setup_test():
        """
        Creates a bst project with dependencydepth + 1 elements, each of which
        depends of the previous element to be created. Each element created
        is of type import and has an empty source file.
        """
        os.mkdir(project_path)

        result = cli.run(silent=True, args=["init", "--project-name", project_name, project_path])
        result.assert_success()

        sourcefiles_path = os.path.join(project_path, "files")
        os.mkdir(sourcefiles_path)

        element_path = os.path.join(project_path, "elements")
        for i in range(0, dependency_depth + 1):
            element = {
                "kind": "import",
                "sources": [{"kind": "local", "path": "files/source{}".format(str(i))}],
                "depends": ["element{}.bst".format(str(i - 1))],
            }
            if i == 0:
                del element["depends"]
            _yaml.roundtrip_dump(element, os.path.join(element_path, "element{}.bst".format(str(i))))

            source = os.path.join(sourcefiles_path, "source{}".format(str(i)))
            open(source, "x", encoding="utf-8").close()  # pylint: disable=consider-using-with
            assert os.path.exists(source)

    setup_test()
    result = cli.run(project=project_path, silent=True, args=["show", "element{}.bst".format(str(dependency_depth))])

    recursion_limit = sys.getrecursionlimit()
    if dependency_depth <= recursion_limit:
        result.assert_success()
    else:
        #  Assert exception is thown and handled
        assert not result.unhandled_exception
        assert result.exit_code == -1

    shutil.rmtree(project_path)


###############################################################
#                   Testing format symbols                    #
###############################################################
@pytest.mark.datafiles(os.path.join(DATA_DIR, "project"))
@pytest.mark.parametrize(
    "dep_kind, expected_deps",
    [
        ("%{deps}", "- import-dev.bst\n- import-links.bst\n- import-bin.bst"),
        ("%{build-deps}", "- import-dev.bst\n- import-links.bst"),
        ("%{runtime-deps}", "- import-links.bst\n- import-bin.bst"),
    ],
    ids=["deps", "build-deps", "runtime-deps"],
)
def test_format_deps(cli, datafiles, dep_kind, expected_deps):
    project = str(datafiles)
    target = "format-deps.bst"
    result = cli.run(project=project, silent=True, args=["show", "--deps", "none", "--format", dep_kind, target])
    result.assert_success()

    expected = "{deps}".format(deps=expected_deps)
    if result.output.strip() != expected:
        raise AssertionError("Expected output:\n{}\nInstead received output:\n{}".format(expected, result.output))


# This tests the resolved value of the 'max-jobs' variable,
# ensuring at least that the variables are resolved according
# to how the user has configured max-jobs
#
@pytest.mark.datafiles(os.path.join(DATA_DIR, "project"))
@pytest.mark.parametrize(
    "cli_value, config_value",
    [
        (None, None),
        (None, "16"),
        ("16", None),
        ("5", "16"),
        ("0", "16"),
        ("16", "0"),
    ],
)
def test_max_jobs(cli, datafiles, cli_value, config_value):
    project = str(datafiles)
    target = "target.bst"

    # Specify `--max-jobs` if this test sets it
    args = []
    if cli_value is not None:
        args += ["--max-jobs", cli_value]
    args += ["show", "--deps", "none", "--format", "%{vars}", target]

    # Specify `max-jobs` in user configuration if this test sets it
    if config_value is not None:
        cli.configure({"build": {"max-jobs": config_value}})

    result = cli.run(project=project, silent=True, args=args)
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    loaded_value = loaded.get_int("max-jobs")

    # We expect the value provided on the command line to take
    # precedence over the configuration file value, if specified.
    #
    # If neither are specified then we expect the default
    expected_value = cli_value or config_value or "0"

    if expected_value == "0":
        # If we are expecting the automatic behavior of using the maximum
        # number of cores available, just check that it is a value > 0
        assert loaded_value > 0, "Automatic setting of max-jobs didnt work"
    else:
        # Check that we got the explicitly set value
        assert loaded_value == int(expected_value)


# This tests that cache keys behave as expected when
# dependencies have been specified as `strict` and
# when building in strict mode.
#
# This test will:
#
#  * Build the target once (and assert that it is cached)
#  * Modify some local files which are imported
#    by an import element which the target depends on
#  * Assert that the cached state of the target element
#    is as expected
#
# We run the test twice, once with an element which strict
# depends on the changing import element, and one which
# depends on it regularly.
#
@pytest.mark.datafiles(os.path.join(DATA_DIR, "strict-depends"))
@pytest.mark.parametrize(
    "target, expected_state",
    [
        ("non-strict-depends.bst", "cached"),
        ("strict-depends.bst", "waiting"),
    ],
)
def test_strict_dependencies(cli, datafiles, target, expected_state):
    project = str(datafiles)

    # Configure non strict mode, this will have
    # an effect on the build and the `bst show`
    # commands run via cli.get_element_states()
    cli.configure({"projects": {"test": {"strict": False}}})

    result = cli.run(project=project, silent=True, args=["build", target])
    result.assert_success()

    states = cli.get_element_states(project, ["base.bst", target])
    assert states["base.bst"] == "cached"
    assert states[target] == "cached"

    # Now modify the file, effectively causing the common base.bst
    # dependency to change it's cache key
    hello_path = os.path.join(project, "files", "hello.txt")
    with open(hello_path, "w", encoding="utf-8") as f:
        f.write("Goodbye")

    # Now assert that we have the states we expect as a result
    states = cli.get_element_states(project, ["base.bst", target])
    assert states["base.bst"] == "buildable"
    assert states[target] == expected_state


@pytest.mark.datafiles(os.path.join(DATA_DIR, "project"))
@pytest.mark.parametrize("fatal", [True, False], ids=["fatal", "non-fatal"])
def test_unaliased_url(cli, tmpdir, datafiles, fatal):
    project = str(datafiles)
    if fatal:
        configure_project(project, {"fatal-warnings": [CoreWarnings.UNALIASED_URL]})

    result = cli.run(project=project, silent=True, args=["show", "unaliased-tar.bst"])

    if fatal:
        result.assert_main_error(ErrorDomain.PLUGIN, CoreWarnings.UNALIASED_URL)
    else:
        result.assert_success()
        assert "WARNING [unaliased-url]" in result.stderr


@pytest.mark.datafiles(os.path.join(DATA_DIR, "project"))
def test_invalid_alias(cli, tmpdir, datafiles):
    project = str(datafiles)
    configure_project(project, {"aliases": {"pony": "https://pony.org/tarballs", "horsy": "http://horsy.tv/shows"}})
    result = cli.run(project=project, silent=True, args=["show", "invalid-alias.bst"])
    result.assert_main_error(ErrorDomain.SOURCE, "invalid-source-alias")
