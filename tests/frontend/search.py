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

# Reuse the nested junction projects from the format tests
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "..",
    "format",
    "junctions",
)


def search(cli, project, *args):
    result = cli.run(project=project, silent=True, args=["search", *args])
    result.assert_success()
    return result.output.splitlines()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "pattern,expected",
    [
        # Basename without extension, across all junctions
        (
            "target",
            [
                "target.bst",
                "subproject.bst:target.bst",
                "subproject.bst:subsubproject.bst:target.bst",
                "subproject.bst:subsubproject.bst:subsubsubproject.bst:target.bst",
            ],
        ),
        # Basename with extension
        ("deeptarget.bst", ["deeptarget.bst"]),
        # Glob
        (
            "subsub*",
            [
                "subproject.bst:subsubproject.bst",
                "subproject.bst:subsubtarget.bst",
                "subproject.bst:subsubproject.bst:subsubsubproject.bst",
            ],
        ),
        # No match
        ("nomatch", []),
    ],
    ids=["basename", "extension", "glob", "nomatch"],
)
def test_search_project(cli, datafiles, pattern, expected):
    project = os.path.join(str(datafiles), "nested")
    assert search(cli, project, pattern) == expected


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "junction,expected",
    [
        (
            "subproject.bst",
            [
                "subproject.bst:target.bst",
                "subproject.bst:subsubproject.bst:target.bst",
                "subproject.bst:subsubproject.bst:subsubsubproject.bst:target.bst",
            ],
        ),
        (
            "subproject.bst:subsubproject.bst",
            [
                "subproject.bst:subsubproject.bst:target.bst",
                "subproject.bst:subsubproject.bst:subsubsubproject.bst:target.bst",
            ],
        ),
    ],
    ids=["junction", "nested-junction"],
)
def test_search_junction(cli, datafiles, junction, expected):
    project = os.path.join(str(datafiles), "nested")
    assert search(cli, project, "target", "--junction", junction) == expected


@pytest.mark.datafiles(DATA_DIR)
def test_search_missing_junction(cli, datafiles):
    project = os.path.join(str(datafiles), "nested")
    result = cli.run(project=project, args=["search", "target", "--junction", "nope.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)
