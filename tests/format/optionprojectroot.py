# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest
from buildstream import _yaml
from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream._testing.runcli import cli  # pylint: disable=unused-import

# Project directory
DATA_DIR = os.path.dirname(os.path.realpath(__file__))


#
# Test that project option conditionals can be resolved in the project root
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("value,expected", [("pony", "a pony"), ("horsy", "a horsy")], ids=["pony", "horsy"])
def test_resolve_project_root_conditional(cli, datafiles, value, expected):
    project = os.path.join(datafiles.dirname, datafiles.basename, "option-project-root")
    result = cli.run(
        project=project,
        silent=True,
        args=["--option", "animal", value, "show", "--deps", "none", "--format", "%{vars}", "element.bst"],
    )
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_str("result") == expected


#
# Test that project option conditionals can be resolved in element overrides
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("value,expected", [("pony", "a pony"), ("horsy", "a horsy")], ids=["pony", "horsy"])
def test_resolve_element_override_conditional(cli, datafiles, value, expected):
    project = os.path.join(datafiles.dirname, datafiles.basename, "option-element-override")
    result = cli.run(
        project=project,
        silent=True,
        args=["--option", "animal", value, "show", "--deps", "none", "--format", "%{vars}", "element.bst"],
    )
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_str("result") == expected


#
# Test that restricted keys error out correctly if specified conditionally
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "project_dir,provenance",
    [
        ("option-restricted-name", "project.conf [line 15 column 10]"),
        ("option-restricted-options", "project.conf [line 16 column 6]"),
    ],
    ids=["name", "options"],
)
def test_restricted_conditionals(cli, datafiles, project_dir, provenance):
    project = os.path.join(datafiles.dirname, datafiles.basename, project_dir)
    result = cli.run(
        project=project,
        silent=True,
        args=["show", "element.bst"],
    )
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.ILLEGAL_COMPOSITE)
    assert provenance in result.stderr
