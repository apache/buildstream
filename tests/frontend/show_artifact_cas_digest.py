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


# This tests that a target that hasn't been built locally
# and that isn't cached remotely has not artifact CAS
# digest.
#
# The test is performed without a remote cache.
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target",
    [
        ("import-basic-files.bst"),
        ("import-executable-files.bst"),
        ("import-symlinks.bst"),
    ],
)
def test_show_artifact_cas_digest_uncached_no_remote(cli, tmpdir, datafiles, target):
    project = str(datafiles)
    expected_no_digest = ""

    # Check the target has not been built locally and is not existing in the remote cache
    assert cli.get_element_state(project, target) != "cached" # May be "buildable" or "waiting" but shouldn't be "cached"

    # Check the target has no artifact digest
    result = cli.run(project=project, silent=True, args=["show", "--format", "%{name},%{artifact-cas-digest}", target])
    result.assert_success()

    received_digest = result.output.splitlines()[0]
    assert received_digest == "{target},{digest}".format(target=target, digest=expected_no_digest)


# This tests that a target that hasn't been built locally
# and that isn't cached remotely has no artifact CAS
# digest.
#
# The test is performed with a remote cache.
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target",
    [
        ("import-basic-files.bst"),
        ("import-executable-files.bst"),
        ("import-symlinks.bst"),
    ],
)
def test_show_artifact_cas_digest_uncached(cli, tmpdir, datafiles, target):
    project = str(datafiles)
    expected_no_digest = ""

    # Configure a local cache
    local_cache = os.path.join(str(tmpdir), "cache")
    cli.configure({"cachedir": local_cache})

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:

        cli.configure({"artifacts": {"servers": [{"url": share.repo}]}})

        # Check the target has not been built locally and is not existing in the remote cache
        assert cli.get_element_state(project, target) == "buildable"
        assert_not_shared(cli, share, project, target)

        # Check the target has no artifact digest
        result = cli.run(project=project, silent=True, args=["show", "--format", "%{name},%{artifact-cas-digest}", target])
        result.assert_success()

        received_digest = result.output.splitlines()[0]
        assert received_digest == "{target},{digest}".format(target=target, digest=expected_no_digest)


# This tests that a target that has been built locally and
# that isn't cached remotely has an artifact CAS digest.
#
# The test is performed with a remote cache.
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target, expected_digest",
    [
        ("import-basic-files.bst", "7093d3c89029932ce1518bd2192e1d3cf60fd88e356b39195d10b87b598c78f0/168"),
        ("import-executable-files.bst", "133a9ae2eda30945a363272ac14bb2c8a941770b5a37c2847c99934f2972ce4f/170"),
        ("import-symlinks.bst", "95947ea55021e26cec4fd4f9de90d2b7f4f7d803ccc91656b3e1f2c9923ddf19/131"),
    ],
)
def test_show_artifact_cas_digest_cached_locally(cli, tmpdir, datafiles, target, expected_digest):
    project = str(datafiles)

    # Configure a local cache
    local_cache = os.path.join(str(tmpdir), "cache")
    cli.configure({"cachedir": local_cache})

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:

        cli.configure({"artifacts": {"servers": [{"url": share.repo}]}})

        # Build the target locally
        result = cli.run(project=project, silent=True, args=["build", target])
        result.assert_success()

        # Check the target has been built locally and is not existing in the remote cache
        assert cli.get_element_state(project, target) == "cached"
        assert_not_shared(cli, share, project, target)

        # Check the target has an artifact digest
        result = cli.run(project=project, silent=True, args=["show", "--format", "%{name},%{artifact-cas-digest}", target])
        result.assert_success()

        received_digest = result.output.splitlines()[0]
        assert received_digest == "{target},{digest}".format(target=target, digest=expected_digest)


# This tests that a target that has been built locally and
# that is cached remotely has an artifact CAS digest.
#
# The test is performed with a remote cache.
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target, expected_digest",
    [
        ("import-basic-files.bst", "7093d3c89029932ce1518bd2192e1d3cf60fd88e356b39195d10b87b598c78f0/168"),
        ("import-executable-files.bst", "133a9ae2eda30945a363272ac14bb2c8a941770b5a37c2847c99934f2972ce4f/170"),
        ("import-symlinks.bst", "95947ea55021e26cec4fd4f9de90d2b7f4f7d803ccc91656b3e1f2c9923ddf19/131"),
    ],
)
def test_show_artifact_cas_digest_cached_remotely(cli, tmpdir, datafiles, target, expected_digest):
    project = str(datafiles)

    # Configure a local cache
    local_cache = os.path.join(str(tmpdir), "cache")
    cli.configure({"cachedir": local_cache})

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:

        cli.configure({"artifacts": {"servers": [{"url": share.repo}]}})

        # Build the target locally
        result = cli.run(project=project, silent=True, args=["build", target])
        result.assert_success()

        # Push the built artifacts to the remote cache
        result = cli.run(project=project, args=["artifact", "push", target, "--artifact-remote", share.repo])
        result.assert_success()

        # Check the target has been built locally and is existing in the remote cache
        assert cli.get_element_state(project, target) == "cached"
        assert_shared(cli, share, project, target)

        # Check the target has an artifact digest
        result = cli.run(project=project, silent=True, args=["show", "--format", "%{name},%{artifact-cas-digest}", target])
        result.assert_success()

        received_digest = result.output.splitlines()[0]
        assert received_digest == "{target},{digest}".format(target=target, digest=expected_digest)


# This tests that a target that has been built locally and
# that is cached remotely has an artifact CAS digest.
#
# The test is performed with a remote cache.
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target",
    [
        ("import-basic-files.bst"),
        ("import-executable-files.bst"),
        ("import-symlinks.bst"),
    ],
)
def test_show_artifact_cas_digest_cached_remotely_only(cli, tmpdir, datafiles, target):
    project = str(datafiles)
    expected_no_digest = ""

    # Configure a local cache
    local_cache = os.path.join(str(tmpdir), "cache")
    cli.configure({"cachedir": local_cache})

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:

        cli.configure({"artifacts": {"servers": [{"url": share.repo}]}})

        # Build the target locally
        result = cli.run(project=project, silent=True, args=["build", target])
        result.assert_success()

        # Push the built artifacts to the remote cache
        result = cli.run(project=project, args=["artifact", "push", target, "--artifact-remote", share.repo])
        result.assert_success()

        # Delete the locally cached target
        result = cli.run(project=project, silent=True, args=["artifact", "delete", target])
        result.assert_success()

        # Check the target has been deleted locally
        assert cli.get_element_state(project, target) == "buildable"
        assert_shared(cli, share, project, target)
        
        # Check the target has an artifact digest
        result = cli.run(project=project, silent=True, args=["show", "--format", "%{name},%{artifact-cas-digest}", target])
        result.assert_success()

        received_digest = result.output.splitlines()[0]
        assert received_digest == "{target},{digest}".format(target=target, digest=expected_no_digest)


# This tests that the target and its dependencies are built
# as expected and that all their artifact CAS digests are
# available.
#
# The test is performed without a remote cache.
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target, expected_digests",
    [
        ("dependencies.bst", {
            "dependencies.bst": "7093d3c89029932ce1518bd2192e1d3cf60fd88e356b39195d10b87b598c78f0/168",
            "import-symlinks.bst": "95947ea55021e26cec4fd4f9de90d2b7f4f7d803ccc91656b3e1f2c9923ddf19/131",
        }),
    ],
)
def test_show_artifact_cas_digest_dependencies(cli, tmpdir, datafiles, target, expected_digests):
    project = str(datafiles)
    expected_no_digest = ""

    # Check the target and its dependencies have not been built locally
    for component in sorted(expected_digests.keys()):
        assert cli.get_element_state(project, component) != "cached" # May be "buildable" or "waiting" but shouldn't be "cached"

    # Check the target and its dependencies have no artifact digest
    result = cli.run(project=project, silent=True, args=["show", "--format", "%{name},%{artifact-cas-digest}", target])
    result.assert_success()

    digests = dict(line.split(",", 2) for line in result.output.splitlines())
    assert len(digests) == len(expected_digests)

    for component, received in sorted(digests.items()):
        assert received == expected_no_digest

    # Build the target and its dependencies locally
    result = cli.run(project=project, silent=True, args=["build", target])
    result.assert_success()

    # Check the target and its dependencies have been built locally
    for component in sorted(expected_digests.keys()):
        assert cli.get_element_state(project, component) == "cached"

    # Check the target and its dependencies have an artifact digest
    result = cli.run(project=project, silent=True, args=["show", "--format", "%{name},%{artifact-cas-digest}", target])
    result.assert_success()

    digests = dict(line.split(",", 2) for line in result.output.splitlines())
    assert len(digests) == len(expected_digests)

    for component, received in sorted(digests.items()):
        assert received == expected_digests[component]
