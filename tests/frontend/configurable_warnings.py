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

from buildstream.plugin import CoreWarnings
from buildstream.exceptions import ErrorDomain
from buildstream import _yaml
from buildstream._testing.runcli import cli  # pylint: disable=unused-import

TOP_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "configuredwarning")


def get_project(fatal_warnings):
    return {
        "name": "test",
        "min-version": "2.0",
        "element-path": "elements",
        "plugins": [{"origin": "local", "path": "plugins", "elements": ["warninga", "warningb", "corewarn"]}],
        "fatal-warnings": fatal_warnings,
    }


def build_project(datafiles, fatal_warnings):
    project_path = str(datafiles)

    project = get_project(fatal_warnings)

    _yaml.roundtrip_dump(project, os.path.join(project_path, "project.conf"))

    return project_path


@pytest.mark.datafiles(TOP_DIR)
@pytest.mark.parametrize(
    "element_name, fatal_warnings, expect_fatal, error_domain",
    [
        ("corewarn.bst", [CoreWarnings.OVERLAPS], True, ErrorDomain.STREAM),
        ("warninga.bst", ["warninga:warning-a"], True, ErrorDomain.STREAM),
        ("warningb.bst", ["warningb:warning-b"], True, ErrorDomain.STREAM),
        ("corewarn.bst", [], False, None),
        ("warninga.bst", [], False, None),
        ("warningb.bst", [], False, None),
        ("warninga.bst", [CoreWarnings.OVERLAPS], False, None),
        ("warningb.bst", [CoreWarnings.OVERLAPS], False, None),
    ],
)
def test_fatal_warnings(cli, datafiles, element_name, fatal_warnings, expect_fatal, error_domain):
    project_path = build_project(datafiles, fatal_warnings)

    result = cli.run(project=project_path, args=["build", element_name])
    if expect_fatal:
        result.assert_main_error(error_domain, None, "Expected fatal execution")
    else:
        result.assert_success("Unexpected fatal execution")
