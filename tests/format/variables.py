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


@pytest.mark.parametrize("element", ["manual.bst", "manual2.bst"])
@pytest.mark.datafiles(os.path.join(DATA_DIR, "missing_variables"))
def test_missing_variable(cli, datafiles, element):
    project = str(datafiles)
    result = cli.run(project=project, silent=True, args=["show", "--deps", "none", "--format", "%{config}", element])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.UNRESOLVED_VARIABLE)


@pytest.mark.timeout(3, method="signal")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "cyclic_variables"))
def test_cyclic_variables(cli, datafiles):
    print_warning("Performing cyclic test, if this test times out it will " + "exit the test sequence")
    project = str(datafiles)
    result = cli.run(project=project, silent=True, args=["build", "cyclic.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.RECURSIVE_VARIABLE)


@pytest.mark.parametrize("protected_var", PROTECTED_VARIABLES)
@pytest.mark.datafiles(os.path.join(DATA_DIR, "protected-vars"))
def test_use_of_protected_var_project_conf(cli, datafiles, protected_var):
    project = str(datafiles)
    conf = {"name": "test", "variables": {protected_var: "some-value"}}
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
    conf = {"name": "test", "elements": {"manual": {"variables": {protected_var: "some-value"}}}}
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
