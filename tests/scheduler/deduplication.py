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
import shutil
import pytest

from buildstream._testing import cli  # pylint: disable=unused-import
from buildstream.exceptions import ErrorDomain

from tests.testutils import create_artifact_share

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "deduplication",
)


# Elements sharing a strong cache key are built only once
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("strict", [True, False], ids=["strict", "non-strict"])
def test_build(cli, datafiles, strict):
    project = os.path.join(str(datafiles), "simple")
    cli.configure({"projects": {"deduplication-simple": {"strict": strict}}})

    assert cli.get_element_key(project, "a.bst") == cli.get_element_key(project, "b.bst")

    result = cli.run(project=project, args=["build", "a.bst", "b.bst"])
    result.assert_success()
    assert len(result.get_built_elements()) == 1

    states = cli.get_element_states(project, ["a.bst", "b.bst"])
    assert states == {"a.bst": "cached", "b.bst": "cached"}


# The same element loaded through two junctions is built only once
@pytest.mark.datafiles(DATA_DIR)
def test_build_junctions(cli, datafiles):
    project = os.path.join(str(datafiles), "multi-stage")

    result = cli.run(project=project, args=["build", "a.bst", "b.bst"])
    result.assert_success()

    built = [element for element in result.get_built_elements() if element.endswith(":hello.bst")]
    assert len(built) == 1

    states = cli.get_element_states(project, ["subproject-a.bst:hello.bst", "subproject-b.bst:hello.bst"])
    assert set(states.values()) == {"cached"}


# When the build of an element fails, the elements waiting for it are built
@pytest.mark.datafiles(DATA_DIR)
def test_build_failure(cli, datafiles):
    project = os.path.join(str(datafiles), "failure")

    result = cli.run(project=project, args=["--on-error", "continue", "build", "a.bst", "b.bst"])
    result.assert_main_error(ErrorDomain.STREAM, None)

    assert sorted(result.get_start_order("build")) == ["a.bst", "b.bst"]

    states = cli.get_element_states(project, ["a.bst", "b.bst"])
    assert states == {"a.bst": "failed", "b.bst": "failed"}


# Elements sharing a strong cache key are pulled only once
@pytest.mark.datafiles(DATA_DIR)
def test_pull(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "simple")

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:
        cli.configure({"artifacts": {"servers": [{"url": share.repo, "push": True}]}})

        result = cli.run(project=project, args=["build", "a.bst", "b.bst"])
        result.assert_success()

        # Wipe the local cache so that the artifacts must be pulled
        shutil.rmtree(os.path.join(cli.directory, "cas"))
        shutil.rmtree(os.path.join(cli.directory, "artifacts"))

        result = cli.run(project=project, args=["artifact", "pull", "a.bst", "b.bst"])
        result.assert_success()
        assert len(result.get_pulled_elements()) == 1

        states = cli.get_element_states(project, ["a.bst", "b.bst"])
        assert states == {"a.bst": "cached", "b.bst": "cached"}
