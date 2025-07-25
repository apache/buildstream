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

from buildstream._testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream._testing._utils.site import HAVE_SANDBOX

pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


# Test that the digest environment variable is set correctly during a build
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_build_base(cli, datafiles):
    project = str(datafiles)
    element_name = "digest-environment/base.bst"

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0


# Test that the digest environment variable is not affected by unrelated build dependencies
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_build_base_plus_extra_dep(cli, datafiles):
    project = str(datafiles)
    element_name = "digest-environment/base-plus-extra-dep.bst"

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0


# Test that multiple dependencies can be merged into a single digest environment variable
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_build_merge(cli, datafiles):
    project = str(datafiles)
    element_name = "digest-environment/merge.bst"

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0


# Test that multiple digest environment variables can be configured in a single element
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_build_two(cli, datafiles):
    project = str(datafiles)
    element_name = "digest-environment/two.bst"

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0


# Test that the digest environment variable is also set in a build shell
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_build_shell(cli, datafiles):
    project = str(datafiles)
    element_name = "digest-environment/base.bst"

    # Ensure artifacts of build dependencies are available for build shell
    result = cli.run(project=project, args=["build", "--deps", "build", element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["shell", "--build", element_name, "--", "sh", "-c", "echo $BASE_DIGEST"])
    assert result.exit_code == 0
    assert result.output.strip() == "63450d93eab71f525d08378fe50960aff92b0ec8f1b0be72b2ac4b8259d09833/1227"


# Test that the digest environment variable is also set in a build shell staged from a buildtree
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_build_shell_buildtree(cli, datafiles):
    project = str(datafiles)
    element_name = "digest-environment/base-buildtree.bst"

    # Generate buildtree
    result = cli.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
    assert result.exit_code == 0

    result = cli.run(
        project=project,
        args=["shell", "--build", "--use-buildtree", element_name, "--", "sh", "-c", "echo $BASE_DIGEST"],
    )
    assert result.exit_code == 0
    assert result.output.strip() == "63450d93eab71f525d08378fe50960aff92b0ec8f1b0be72b2ac4b8259d09833/1227"
