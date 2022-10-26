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
from buildstream._testing.runcli import cli  # pylint: disable=unused-import

# Project directory
DATA_DIR = os.path.dirname(os.path.realpath(__file__))


@pytest.mark.datafiles(DATA_DIR)
def test_project_error(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "list-directive-error-project")
    result = cli.run(
        project=project, silent=True, args=["show", "--deps", "none", "--format", "%{vars}", "element.bst"]
    )

    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.TRAILING_LIST_DIRECTIVE)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("target", [("variables.bst"), ("environment.bst"), ("config.bst"), ("public.bst")])
def test_element_error(cli, datafiles, target):
    project = os.path.join(datafiles.dirname, datafiles.basename, "list-directive-error-element")
    result = cli.run(project=project, silent=True, args=["show", "--deps", "none", "--format", "%{vars}", target])

    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.TRAILING_LIST_DIRECTIVE)


@pytest.mark.datafiles(DATA_DIR)
def test_project_composite_error(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "list-directive-type-error")
    result = cli.run(
        project=project, silent=True, args=["show", "--deps", "none", "--format", "%{vars}", "element.bst"]
    )

    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.ILLEGAL_COMPOSITE)
