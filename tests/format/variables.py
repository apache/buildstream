# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import sys

import pytest

from buildstream import _yaml
from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream.testing.runcli import cli  # pylint: disable=unused-import


# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "variables")

# List of BuildStream protected variables
PROTECTED_VARIABLES = [("project-name"), ("element-name"), ("max-jobs")]


def print_warning(msg):
    RED, END = "\033[91m", "\033[0m"
    print(("\n{}{}{}").format(RED, msg, END), file=sys.stderr)


###############################################################
#  Test proper loading of some default commands from plugins  #
###############################################################
@pytest.mark.parametrize(
    "target,varname,expected", [("autotools.bst", "make-install", 'make -j1 DESTDIR="/buildstream-install" install')],
)
@pytest.mark.datafiles(os.path.join(DATA_DIR, "defaults"))
def test_defaults(cli, datafiles, target, varname, expected):
    project = str(datafiles)
    result = cli.run(project=project, silent=True, args=["show", "--deps", "none", "--format", "%{vars}", target])
    result.assert_success()
    result_vars = _yaml.load_data(result.output)
    assert result_vars.get_str(varname) == expected


################################################################
#  Test overriding of variables to produce different commands  #
################################################################
@pytest.mark.parametrize(
    "target,varname,expected", [("autotools.bst", "make-install", 'make -j1 DESTDIR="/custom/install/root" install')],
)
@pytest.mark.datafiles(os.path.join(DATA_DIR, "overrides"))
def test_overrides(cli, datafiles, target, varname, expected):
    project = str(datafiles)
    result = cli.run(project=project, silent=True, args=["show", "--deps", "none", "--format", "%{vars}", target])
    result.assert_success()
    result_vars = _yaml.load_data(result.output)
    assert result_vars.get_str(varname) == expected


@pytest.mark.parametrize(
    "element,provenance",
    [
        # This test makes a reference to an undefined variable in a build command
        ("manual.bst", "manual.bst [line 5 column 6]"),
        # This test makes a reference to an undefined variable by another variable,
        # ensuring that we validate variables even when they are unused
        ("manual2.bst", "manual2.bst [line 4 column 8]"),
        # This test uses a build command to refer to some variables which ultimately
        # refer to an undefined variable, testing a more complex case.
        ("manual3.bst", "manual3.bst [line 6 column 8]"),
    ],
    ids=["build-command", "variables", "complex"],
)
@pytest.mark.datafiles(os.path.join(DATA_DIR, "missing_variables"))
def test_undefined(cli, datafiles, element, provenance):
    project = str(datafiles)
    result = cli.run(project=project, silent=True, args=["show", "--deps", "none", "--format", "%{config}", element])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.UNRESOLVED_VARIABLE)
    assert provenance in result.stderr


@pytest.mark.parametrize(
    "element,provenances",
    [
        # Test a simple a -> b and b -> a reference
        ("simple-cyclic.bst", ["simple-cyclic.bst [line 4 column 5]", "simple-cyclic.bst [line 5 column 5]"]),
        # Test a simple a -> b and b -> a reference with some text involved
        ("cyclic.bst", ["cyclic.bst [line 5 column 10]", "cyclic.bst [line 4 column 5]"]),
        # Test an indirect circular dependency
        (
            "indirect-cyclic.bst",
            [
                "indirect-cyclic.bst [line 5 column 5]",
                "indirect-cyclic.bst [line 6 column 5]",
                "indirect-cyclic.bst [line 7 column 5]",
                "indirect-cyclic.bst [line 8 column 5]",
            ],
        ),
        # Test an indirect circular dependency
        ("self-reference.bst", ["self-reference.bst [line 4 column 5]"]),
    ],
    ids=["simple", "simple-text", "indirect", "self-reference"],
)
@pytest.mark.timeout(30, method="signal")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "cyclic_variables"))
def test_circular_reference(cli, datafiles, element, provenances):
    print_warning("Performing cyclic test, if this test times out it will exit the test sequence")
    project = str(datafiles)
    result = cli.run(project=project, silent=True, args=["build", element])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.CIRCULAR_REFERENCE_VARIABLE)
    for provenance in provenances:
        assert provenance in result.stderr


# Test that variables which refer to eachother very deeply are
# still resolved correctly, this ensures that we are not relying
# on a recursive algorithm limited by stack depth.
#
@pytest.mark.parametrize(
    "maxvars", [50, 500, 5000],
)
@pytest.mark.datafiles(os.path.join(DATA_DIR, "defaults"))
def test_deep_references(cli, datafiles, maxvars):
    project = str(datafiles)

    # Generate an element with very, very many variables to resolve,
    # each which expand to the value of the previous variable.
    #
    # The bottom variable defines a test value which we check for
    # in the top variable in `bst show` output.
    #
    topvar = "var{}".format(maxvars)
    bottomvar = "var0"
    testvalue = "testvalue {}".format(maxvars)

    # Generate
    variables = {"var{}".format(idx + 1): "%{var" + str(idx) + "}" for idx in range(maxvars)}
    variables[bottomvar] = testvalue
    element = {"kind": "manual", "variables": variables}
    _yaml.roundtrip_dump(element, os.path.join(project, "test.bst"))

    # Run `bst show`
    result = cli.run(project=project, args=["show", "--format", "%{vars}", "test.bst"])
    result.assert_success()

    # Test results
    result_vars = _yaml.load_data(result.output)
    assert result_vars.get_str(topvar) == testvalue


@pytest.mark.parametrize("protected_var", PROTECTED_VARIABLES)
@pytest.mark.datafiles(os.path.join(DATA_DIR, "protected-vars"))
def test_use_of_protected_var_project_conf(cli, datafiles, protected_var):
    project = str(datafiles)
    conf = {"name": "test", "min-version": "2.0", "variables": {protected_var: "some-value"}}
    _yaml.roundtrip_dump(conf, os.path.join(project, "project.conf"))

    element = {
        "kind": "import",
        "sources": [{"kind": "local", "path": "foo.txt"}],
    }
    _yaml.roundtrip_dump(element, os.path.join(project, "target.bst"))

    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.PROTECTED_VARIABLE_REDEFINED)


@pytest.mark.parametrize("protected_var", PROTECTED_VARIABLES)
@pytest.mark.datafiles(os.path.join(DATA_DIR, "protected-vars"))
def test_use_of_protected_var_element_overrides(cli, datafiles, protected_var):
    project = str(datafiles)
    conf = {"name": "test", "min-version": "2.0", "elements": {"manual": {"variables": {protected_var: "some-value"}}}}
    _yaml.roundtrip_dump(conf, os.path.join(project, "project.conf"))

    element = {
        "kind": "manual",
        "sources": [{"kind": "local", "path": "foo.txt"}],
    }
    _yaml.roundtrip_dump(element, os.path.join(project, "target.bst"))

    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.PROTECTED_VARIABLE_REDEFINED)


@pytest.mark.parametrize("protected_var", PROTECTED_VARIABLES)
@pytest.mark.datafiles(os.path.join(DATA_DIR, "protected-vars"))
def test_use_of_protected_var_in_element(cli, datafiles, protected_var):
    project = str(datafiles)
    element = {
        "kind": "import",
        "sources": [{"kind": "local", "path": "foo.txt"}],
        "variables": {protected_var: "some-value"},
    }
    _yaml.roundtrip_dump(element, os.path.join(project, "target.bst"))

    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.PROTECTED_VARIABLE_REDEFINED)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "shared_variables"))
def test_variables_are_resolved_in_elements_context(cli, datafiles):
    project = str(datafiles)

    result = cli.run(project=project, args=["build"])
    result.assert_success()

    checkout_dir = os.path.join(project, "checkout")
    for elem in ["one", "two"]:
        result = cli.run(
            project=project,
            args=["artifact", "checkout", "--directory", os.path.join(checkout_dir, elem), "{}.bst".format(elem)],
        )
        result.assert_success()

    assert (os.listdir(os.path.join(checkout_dir, "one")), os.listdir(os.path.join(checkout_dir, "two"))) == (
        ["one.bst"],
        ["two.bst"],
    )


@pytest.mark.datafiles(os.path.join(DATA_DIR, "public_data_variables"))
def test_variables_are_resolved_in_public_section(cli, datafiles):
    project = str(datafiles)

    result = cli.run(project=project, args=["show", "--format", "%{public}", "public.bst"])
    result.assert_success()

    output = _yaml.load_data(result.output).strip_node_info()
    expected = {"integration-commands": ["echo expanded"], "test": "expanded"}

    assert {k: v for k, v in output.items() if k in expected} == expected


@pytest.mark.datafiles(os.path.join(DATA_DIR, "public_data_variables"))
def test_variables_resolving_errors_in_public_section(cli, datafiles):
    project = str(datafiles)

    result = cli.run(project=project, args=["show", "--format", "%{public}", "public_unresolved.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.UNRESOLVED_VARIABLE)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "partial_context"))
def test_partial_context_junctions(cli, datafiles):
    project = str(datafiles)

    result = cli.run(project=project, args=["show", "--format", "%{vars}", "test.bst"])
    result.assert_success()
    result_vars = _yaml.load_data(result.output)
    assert result_vars.get_str("eltvar") == "/bar/foo/baz"
