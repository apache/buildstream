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
from buildstream._testing.integration import assert_contains
from buildstream._testing._utils.site import HAVE_SANDBOX

pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_remote_execution(cli, datafiles):
    project = str(datafiles)
    checkout1 = os.path.join(cli.directory, "checkout1")
    checkout2 = os.path.join(cli.directory, "checkout2")
    element_name = "recc/remoteexecution.bst"

    # Always cache buildtrees to be able to check recc logs
    result = cli.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
    if result.exit_code != 0:
        # Output recc logs in case of failure
        cli.run(
            project=project,
            args=[
                "shell",
                "--build",
                "--use-buildtree",
                element_name,
                "--",
                "sh",
                "-c",
                "cat config.log .recc-log/* */.recc-log/*",
            ],
        )
    assert result.exit_code == 0

    result = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout1])
    assert result.exit_code == 0

    assert_contains(
        checkout1,
        [
            "/usr",
            "/usr/bin",
            "/usr/share",
            "/usr/bin/hello",
            "/usr/share/doc",
            "/usr/share/doc/amhello",
            "/usr/share/doc/amhello/README",
        ],
    )

    # Check the main build log
    result = cli.run(project=project, args=["artifact", "log", element_name])
    assert result.exit_code == 0
    log = result.output

    # Verify we get expected output exactly once
    assert log.count("Making all in src") == 1

    result = cli.run(
        project=project,
        args=[
            "shell",
            "--build",
            "--use-buildtree",
            element_name,
            "--",
            "sh",
            "-c",
            "cat src/.recc-log/recc.buildbox*",
        ],
    )
    assert result.exit_code == 0
    recc_log = result.output

    # Verify recc is successfully using remote execution for both, compiling and linking
    assert recc_log.count("Executing action remotely") == 2
    assert recc_log.count("Remote execution finished with exit code 0") == 2

    # Delete artifact from BuildStream cache to trigger a BuildStream rebuild with action cache hits for recc
    result = cli.run(project=project, args=["artifact", "delete", element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout2])
    assert result.exit_code == 0

    assert_contains(
        checkout2,
        [
            "/usr",
            "/usr/bin",
            "/usr/share",
            "/usr/bin/hello",
            "/usr/share/doc",
            "/usr/share/doc/amhello",
            "/usr/share/doc/amhello/README",
        ],
    )

    result = cli.run(
        project=project,
        args=[
            "shell",
            "--build",
            "--use-buildtree",
            element_name,
            "--",
            "sh",
            "-c",
            "cat src/.recc-log/recc.buildbox*",
        ],
    )
    assert result.exit_code == 0
    recc_log = result.output

    # Verify recc is getting action cache hits for both, compiling and linking
    assert recc_log.count("Action Cache hit") == 2


@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_cache_only(cli, datafiles):
    project = str(datafiles)
    checkout1 = os.path.join(cli.directory, "checkout1")
    checkout2 = os.path.join(cli.directory, "checkout2")
    element_name = "recc/cacheonly.bst"

    # Always cache buildtrees to be able to check recc logs
    result = cli.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
    if result.exit_code != 0:
        # Output recc logs in case of failure
        cli.run(
            project=project,
            args=[
                "shell",
                "--build",
                "--use-buildtree",
                element_name,
                "--",
                "sh",
                "-c",
                "cat config.log .recc-log/* */.recc-log/*",
            ],
        )
    assert result.exit_code == 0

    result = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout1])
    assert result.exit_code == 0

    assert_contains(
        checkout1,
        [
            "/usr",
            "/usr/bin",
            "/usr/share",
            "/usr/bin/hello",
            "/usr/share/doc",
            "/usr/share/doc/amhello",
            "/usr/share/doc/amhello/README",
        ],
    )

    # Check the main build log
    result = cli.run(project=project, args=["artifact", "log", element_name])
    assert result.exit_code == 0
    log = result.output

    # Verify we get expected output exactly once
    assert log.count("Making all in src") == 1

    result = cli.run(
        project=project,
        args=[
            "shell",
            "--build",
            "--use-buildtree",
            element_name,
            "--",
            "sh",
            "-c",
            "cat src/.recc-log/recc.buildbox*",
        ],
    )
    assert result.exit_code == 0
    recc_log = result.output

    # Verify recc is using local execution for both, compiling and linking
    assert recc_log.count("Action not cached and running in cache-only mode, executing locally") == 2

    # Delete artifact from BuildStream cache to trigger a BuildStream rebuild with action cache hits for recc
    result = cli.run(project=project, args=["artifact", "delete", element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout2])
    assert result.exit_code == 0

    assert_contains(
        checkout2,
        [
            "/usr",
            "/usr/bin",
            "/usr/share",
            "/usr/bin/hello",
            "/usr/share/doc",
            "/usr/share/doc/amhello",
            "/usr/share/doc/amhello/README",
        ],
    )

    result = cli.run(
        project=project,
        args=[
            "shell",
            "--build",
            "--use-buildtree",
            element_name,
            "--",
            "sh",
            "-c",
            "cat src/.recc-log/recc.buildbox*",
        ],
    )
    assert result.exit_code == 0
    recc_log = result.output

    # Verify recc is getting action cache hits for both, compiling and linking
    assert recc_log.count("Action Cache hit") == 2
