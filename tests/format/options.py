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
from buildstream import _yaml
from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream._testing.runcli import cli  # pylint: disable=unused-import

# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "options")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "project_dir",
    [
        ("invalid-name-spaces"),
        ("invalid-name-dashes"),
        ("invalid-name-plus"),
        ("invalid-name-leading-number"),
    ],
)
def test_invalid_option_name(cli, datafiles, project_dir):
    project = os.path.join(datafiles.dirname, datafiles.basename, project_dir)
    result = cli.run(project=project, silent=True, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_SYMBOL_NAME)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "project_dir",
    [
        ("invalid-variable-name-spaces"),
        ("invalid-variable-name-plus"),
    ],
)
def test_invalid_variable_name(cli, datafiles, project_dir):
    project = os.path.join(datafiles.dirname, datafiles.basename, project_dir)
    result = cli.run(project=project, silent=True, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_SYMBOL_NAME)


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_option_type(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "invalid-type")

    # Test with the opt option set
    result = cli.run(
        project=project,
        silent=True,
        args=["--option", "opt", "funny", "show", "--deps", "none", "--format", "%{vars}", "element.bst"],
    )
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_option_cli(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "simple-condition")

    # Test with the opt option set
    result = cli.run(
        project=project,
        silent=True,
        args=["--option", "fart", "funny", "show", "--deps", "none", "--format", "%{vars}", "element.bst"],
    )
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_option_config(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "simple-condition")
    cli.configure({"projects": {"test": {"options": {"fart": "Hello"}}}})
    result = cli.run(
        project=project, silent=True, args=["show", "--deps", "none", "--format", "%{vars}", "element.bst"]
    )
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_expression(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "invalid-expression")
    result = cli.run(
        project=project, silent=True, args=["show", "--deps", "none", "--format", "%{vars}", "element.bst"]
    )
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.EXPRESSION_FAILED)


@pytest.mark.datafiles(DATA_DIR)
def test_undefined(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "undefined-variable")
    result = cli.run(
        project=project, silent=True, args=["show", "--deps", "none", "--format", "%{vars}", "element.bst"]
    )
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.EXPRESSION_FAILED)


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_condition(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "invalid-condition")
    result = cli.run(
        project=project, silent=True, args=["show", "--deps", "none", "--format", "%{vars}", "element.bst"]
    )
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "opt_option,expected_prefix",
    [
        ("False", "/usr"),
        ("True", "/opt"),
    ],
)
def test_simple_conditional(cli, datafiles, opt_option, expected_prefix):
    project = os.path.join(datafiles.dirname, datafiles.basename, "simple-condition")

    # Test with the opt option set
    result = cli.run(
        project=project,
        silent=True,
        args=["--option", "opt", opt_option, "show", "--deps", "none", "--format", "%{vars}", "element.bst"],
    )
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_str("prefix") == expected_prefix


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "debug,logging,expected",
    [
        ("False", "False", "False"),
        ("True", "False", "False"),
        ("False", "True", "False"),
        ("True", "True", "True"),
    ],
)
def test_nested_conditional(cli, datafiles, debug, logging, expected):
    project = os.path.join(datafiles.dirname, datafiles.basename, "nested-condition")

    # Test with the opt option set
    result = cli.run(
        project=project,
        silent=True,
        args=[
            "--option",
            "debug",
            debug,
            "--option",
            "logging",
            logging,
            "show",
            "--deps",
            "none",
            "--format",
            "%{vars}",
            "element.bst",
        ],
    )
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_str("debug") == expected


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "debug,logging,expected",
    [
        ("False", "False", "False"),
        ("True", "False", "False"),
        ("False", "True", "False"),
        ("True", "True", "True"),
    ],
)
def test_compound_and_conditional(cli, datafiles, debug, logging, expected):
    project = os.path.join(datafiles.dirname, datafiles.basename, "compound-and-condition")

    # Test with the opt option set
    result = cli.run(
        project=project,
        silent=True,
        args=[
            "--option",
            "debug",
            debug,
            "--option",
            "logging",
            logging,
            "show",
            "--deps",
            "none",
            "--format",
            "%{vars}",
            "element.bst",
        ],
    )
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_str("debug") == expected


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "debug,logging,expected",
    [
        ("False", "False", "False"),
        ("True", "False", "True"),
        ("False", "True", "True"),
        ("True", "True", "True"),
    ],
)
def test_compound_or_conditional(cli, datafiles, debug, logging, expected):
    project = os.path.join(datafiles.dirname, datafiles.basename, "compound-or-condition")

    # Test with the opt option set
    result = cli.run(
        project=project,
        silent=True,
        args=[
            "--option",
            "debug",
            debug,
            "--option",
            "logging",
            logging,
            "show",
            "--deps",
            "none",
            "--format",
            "%{vars}",
            "element.bst",
        ],
    )
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_str("logging") == expected


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "option,expected",
    [
        ("False", "horsy"),
        ("True", "pony"),
    ],
)
def test_deep_nesting_level1(cli, datafiles, option, expected):
    project = os.path.join(datafiles.dirname, datafiles.basename, "deep-nesting")
    result = cli.run(
        project=project,
        silent=True,
        args=["--option", "pony", option, "show", "--deps", "none", "--format", "%{public}", "element.bst"],
    )
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    shallow_list = loaded.get_sequence("shallow-nest")
    first_dict = shallow_list.mapping_at(0)

    assert first_dict.get_str("animal") == expected


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "option,expected",
    [
        ("False", "horsy"),
        ("True", "pony"),
    ],
)
def test_deep_nesting_level2(cli, datafiles, option, expected):
    project = os.path.join(datafiles.dirname, datafiles.basename, "deep-nesting")
    result = cli.run(
        project=project,
        silent=True,
        args=["--option", "pony", option, "show", "--deps", "none", "--format", "%{public}", "element-deeper.bst"],
    )
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    shallow_list = loaded.get_sequence("deep-nest")
    deeper_list = shallow_list.sequence_at(0)
    first_dict = deeper_list.mapping_at(0)

    assert first_dict.get_str("animal") == expected
