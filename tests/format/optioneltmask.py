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
DATA_DIR = os.path.dirname(os.path.realpath(__file__))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target,value,expected",
    [
        ("pony.bst", "pony.bst", "True"),
        ("horsy.bst", "pony.bst, horsy.bst", "True"),
        ("zebry.bst", "pony.bst, horsy.bst", "False"),
    ],
)
def test_conditional_cli(cli, datafiles, target, value, expected):
    project = os.path.join(datafiles.dirname, datafiles.basename, "option-element-mask")
    result = cli.run(
        project=project,
        silent=True,
        args=["--option", "debug_elements", value, "show", "--deps", "none", "--format", "%{vars}", target],
    )

    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_str("debug") == expected


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target,value,expected",
    [
        ("pony.bst", ["pony.bst"], "True"),
        ("horsy.bst", ["pony.bst", "horsy.bst"], "True"),
        ("zebry.bst", ["pony.bst", "horsy.bst"], "False"),
    ],
)
def test_conditional_config(cli, datafiles, target, value, expected):
    project = os.path.join(datafiles.dirname, datafiles.basename, "option-element-mask")
    cli.configure({"projects": {"test": {"options": {"debug_elements": value}}}})
    result = cli.run(project=project, silent=True, args=["show", "--deps", "none", "--format", "%{vars}", target])

    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_str("debug") == expected


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_declaration(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "option-element-mask-invalid")
    result = cli.run(project=project, silent=True, args=["show", "--deps", "none", "--format", "%{vars}", "pony.bst"])

    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_value(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "option-element-mask")
    result = cli.run(
        project=project,
        silent=True,
        args=["--option", "debug_elements", "kitten.bst", "show", "--deps", "none", "--format", "%{vars}", "pony.bst"],
    )

    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)
