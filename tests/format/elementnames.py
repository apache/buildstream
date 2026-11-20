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


@pytest.mark.parametrize(
    "target,domain,reason,provenance",
    [
        # When specifying a bad suffix on the command line we get a different error, we
        # catch this error earlier on in the load sequence while sorting out element and
        # artifact names and glob expressions.
        #
        ("farm.pony", ErrorDomain.STREAM, "invalid-element-names", None),
        ('The "quoted" pony.bst', ErrorDomain.LOAD, LoadErrorReason.BAD_CHARACTERS_IN_NAME, None),
        (
            "bad-suffix-dep.bst",
            ErrorDomain.LOAD,
            LoadErrorReason.BAD_ELEMENT_SUFFIX,
            "bad-suffix-dep.bst [line 3 column 2]",
        ),
        (
            "bad-chars-dep.bst",
            ErrorDomain.LOAD,
            LoadErrorReason.BAD_CHARACTERS_IN_NAME,
            "bad-chars-dep.bst [line 3 column 2]",
        ),
    ],
    ids=["toplevel-bad-suffix", "toplevel-bad-chars", "dependency-bad-suffix", "dependency-bad-chars"],
)
@pytest.mark.datafiles(DATA_DIR)
def test_invalid_element_names(cli, datafiles, target, domain, reason, provenance):
    project = os.path.join(str(datafiles), "elementnames")
    result = cli.run(project=project, silent=True, args=["show", target])
    result.assert_main_error(domain, reason)
    if provenance:
        assert provenance in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_dotdot_dependency(cli, datafiles):
    project = os.path.join(str(datafiles), "elementnames")
    result = cli.run(project=project, silent=True, args=["show", "dotdot-dep.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.PROJ_PATH_INVALID)
    assert "dotdot-dep.bst [line 3 column 2]" in result.stderr


@pytest.mark.parametrize(
    "target,link,link_target,message",
    [
        ("symlink-dep.bst", "link.bst", "target.bst", "is a symlink"),
        ("symlink-dir-dep.bst", "linkdir", ".", "is a symlink"),
        ("symlink-dep.bst", "link.bst", "../outside.bst", "resolves to a path outside `element-path`"),
    ],
    ids=["file", "directory", "outside-element-path"],
)
@pytest.mark.datafiles(DATA_DIR)
def test_symlink_dependency(cli, datafiles, target, link, link_target, message):
    project = os.path.join(str(datafiles), "elementnames")

    # Valid element outside of the project, only reachable via symlink
    with open(os.path.join(str(datafiles), "outside.bst"), "w", encoding="utf-8") as f:
        f.write("kind: stack\n")

    os.symlink(link_target, os.path.join(project, link))
    result = cli.run(project=project, silent=True, args=["show", target])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.PROJ_PATH_INVALID)
    assert "{} [line 3 column 2]".format(target) in result.stderr
    assert message in result.stderr
