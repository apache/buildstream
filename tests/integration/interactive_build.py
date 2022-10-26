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
import pexpect
import pytest

from buildstream._testing import integration_cache  # pylint: disable=unused-import
from buildstream._testing import runcli
from buildstream._testing._utils.site import HAVE_SANDBOX
from tests.testutils.constants import PEXPECT_TIMEOUT_SHORT, PEXPECT_TIMEOUT_LONG


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


# This fixture launches a `bst build` of given element, and returns a
# `pexpect.spawn` object for the interactive session.
@pytest.fixture
def build_session(integration_cache, datafiles, element_name):
    project = str(datafiles)

    # Spawn interactive session using `configured()` context manager in order
    # to get the same config file as the `cli` fixture.
    with runcli.configured(project, config={"sourcedir": integration_cache.sources}) as config_file:
        session = pexpect.spawn(
            "bst",
            [
                "--directory",
                project,
                "--config",
                config_file,
                "--no-colors",
                "build",
                element_name,
            ],
            timeout=PEXPECT_TIMEOUT_SHORT,
        )
        yield session


# Verify that BuildStream exits cleanly on any of the following choices.
#
# In our simple test case, there is no practical difference between the
# following choices. In future, we'd like to test their behavior separately.
# Currently, this just verifies that BuildStream doesn't choke on any of these
# choices.
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("element_name", ["interactive/failed-build.bst"])
@pytest.mark.parametrize("choice", ["continue", "quit", "terminate"])
def test_failed_build_quit(element_name, build_session, choice):
    build_session.expect_exact("Choice: [continue]:", timeout=PEXPECT_TIMEOUT_LONG)
    build_session.sendline(choice)

    build_session.expect_exact(pexpect.EOF)
    build_session.close()
    assert build_session.exitstatus == 255


@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("element_name", ["interactive/failed-build.bst"])
def test_failed_build_retry(element_name, build_session):
    build_session.expect_exact("Choice: [continue]:", timeout=PEXPECT_TIMEOUT_LONG)
    build_session.sendline("retry")

    build_session.expect_exact("Choice: [continue]:", timeout=PEXPECT_TIMEOUT_LONG)
    build_session.sendline("quit")

    build_session.expect_exact(pexpect.EOF)
    build_session.close()
    assert build_session.exitstatus == 255


@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("element_name", ["interactive/failed-build.bst"])
def test_failed_build_log(element_name, build_session):
    build_session.expect_exact("Choice: [continue]:", timeout=PEXPECT_TIMEOUT_LONG)
    build_session.sendline("log")

    # Send a few carriage returns to get to the end of the pager
    build_session.sendline(os.linesep * 20)

    # Assert that we got something from the logs
    build_session.expect("FAILURE interactive/failed-build.bst: Running (build-)?commands")

    # Quit the pager
    build_session.send("q")
    # Quit the session
    build_session.expect_exact("Choice: [continue]:")
    build_session.sendline("quit")

    build_session.expect_exact(pexpect.EOF)
    build_session.close()
    assert build_session.exitstatus == 255


@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("element_name", ["interactive/failed-build.bst"])
def test_failed_build_shell(element_name, build_session):
    build_session.expect_exact("Choice: [continue]:", timeout=PEXPECT_TIMEOUT_LONG)
    build_session.sendline("shell")

    # Wait for shell prompt
    build_session.expect_exact("interactive/failed-build.bst:/buildstream/test/interactive/failed-build.bst]")
    # Verify that we have our sources
    build_session.sendline("ls")
    build_session.expect_exact("test.txt")

    # Quit the shell
    build_session.sendline("exit")
    # Quit the session
    build_session.expect_exact("Choice: [continue]:", timeout=PEXPECT_TIMEOUT_LONG)
    build_session.sendline("quit")

    build_session.expect_exact(pexpect.EOF)
    build_session.close()
    assert build_session.exitstatus == 255
