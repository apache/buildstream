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

from tests.testutils import (
    create_artifact_share,
    assert_shared,
    assert_not_shared,
)


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "show_artifact_cas_digest_project")

# This tests that cache keys behave as expected when
# dependencies have been specified as `strict` and
# when building in strict mode.
#
# This test will:
#
#  * Build the target once (and assert that it is cached)
#  * Modify some local files which are imported
#    by an import element which the target depends on
#  * Assert that the cached state of the target element
#    is as expected
#
# We run the test twice, once with an element which strict
# depends on the changing import element, and one which
# depends on it regularly.
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target, expected_digests",
    [
        ("import-basic-files.bst", {
            "import-basic-files.bst": "7093d3c89029932ce1518bd2192e1d3cf60fd88e356b39195d10b87b598c78f0/168",
        }),
        ("import-executable-files.bst", {
            "import-executable-files.bst": "133a9ae2eda30945a363272ac14bb2c8a941770b5a37c2847c99934f2972ce4f/170",
        }),
        ("import-symlinks.bst", {
            "import-symlinks.bst": "95947ea55021e26cec4fd4f9de90d2b7f4f7d803ccc91656b3e1f2c9923ddf19/131",
        }),
    ],
)
def test_show_artifact_cas_digest(cli, tmpdir, datafiles, target, expected_digests):
    project = str(datafiles)
    expected_no_digest = ""

    # Configure a local cache
    local_cache = os.path.join(str(tmpdir), "cache")
    cli.configure({"cachedir": local_cache})

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:

        cli.configure({"artifacts": {"servers": [{"url": share.repo}]}})

        # Check the element and its dependencies have not been built locally and are not existing in the remote cache
        for component in sorted(expected_digests.keys()):
            assert cli.get_element_state(project, component) == "buildable"
            assert_not_shared(cli, share, project, component)

        # Check the element and its dependencies have no artifact digest
        result = cli.run(project=project, silent=True, args=["show", "--format", "%{name},%{artifact-cas-digest}", target])
        result.assert_success()

        digests = dict(line.split(",", 2) for line in result.output.splitlines())
        assert len(digests) == len(expected_digests)

        for component, received in sorted(digests.items()):
            assert received == expected_no_digest

        # Build the element locally
        result = cli.run(project=project, silent=True, args=["build", target])
        result.assert_success()

        # Check the element and its dependencies have been built locally and are not existing in the remote cache
        for component in sorted(expected_digests.keys()):
            assert cli.get_element_state(project, component) == "cached"
            assert_not_shared(cli, share, project, component)

        # Check the element and its dependencies have an artifact digest
        result = cli.run(project=project, silent=True, args=["show", "--format", "%{name},%{artifact-cas-digest}", target])
        result.assert_success()

        digests = dict(line.split(",", 2) for line in result.output.splitlines())
        assert len(digests) == len(expected_digests)

        for component, received in sorted(digests.items()):
            assert received == expected_digests[component]

        # Push the built artifacts to the remote cache
        for component in sorted(expected_digests.keys()):
            result = cli.run(project=project, args=["artifact", "push", component, "--artifact-remote", share.repo])
            #result.assert_main_error(ErrorDomain.STREAM, None)

        # Check the element and its dependencies have been built locally and are existing in the remote cache
        for component in sorted(expected_digests.keys()):
            assert cli.get_element_state(project, component) == "cached"
            assert_shared(cli, share, project, component)

        # Delete the locally cached element but not its dependencies
        result = cli.run(project=project, silent=True, args=["artifact", "delete", target])
        result.assert_success()

        # Check the element has been deleted locally
        for component, received in sorted(digests.items()):
            assert cli.get_element_state(project, target) == ("buildable" if component == target else "cached")
            assert_shared(cli, share, project, target)
