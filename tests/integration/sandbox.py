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

from tests.testutils import create_artifact_share

pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_sandbox_shm(cli, datafiles):
    project = str(datafiles)
    element_name = "sandbox/test-dev-shm.bst"

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0


# Test that variable expansion works in build-arch sandbox config.
# Regression test for https://gitlab.com/BuildStream/buildstream/-/issues/1303
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_build_arch(cli, datafiles):
    project = str(datafiles)
    element_name = "sandbox/build-arch.bst"

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0


# Test that the REAPI socket is created in the sandbox.
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_remote_apis_socket(cli, datafiles):
    project = str(datafiles)
    element_name = "sandbox/remote-apis-socket.bst"

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0

    # Verify that loading the artifact succeeds
    artifact_name = cli.get_artifact_name(project, "test", element_name)
    result = cli.run(project=project, args=["artifact", "show", artifact_name])
    assert result.exit_code == 0


# Test configuration with remote action cache for nested REAPI.
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_remote_apis_socket_with_action_cache(cli, tmpdir, datafiles):
    project = str(datafiles)
    element_name = "sandbox/remote-apis-socket.bst"

    with create_artifact_share(os.path.join(str(tmpdir), "remote")) as share:
        cli.configure(
            {
                "remote-execution": {
                    "storage-service": {"url": share.repo},
                    "action-cache-service": {"url": share.repo, "push": True},
                }
            }
        )

        result = cli.run(project=project, args=["build", element_name])
        assert result.exit_code == 0


# Test configuration with remote action cache for nested REAPI with updates enabled.
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_remote_apis_socket_with_action_cache_update(cli, tmpdir, datafiles):
    project = str(datafiles)
    element_name = "sandbox/remote-apis-socket-ac-update.bst"

    with create_artifact_share(os.path.join(str(tmpdir), "remote")) as share:
        cli.configure(
            {
                "remote-execution": {
                    "storage-service": {"url": share.repo},
                    "action-cache-service": {"url": share.repo, "push": True},
                }
            }
        )

        result = cli.run(project=project, args=["build", element_name])
        assert result.exit_code == 0

        # Verify that loading the artifact succeeds
        artifact_name = cli.get_artifact_name(project, "test", element_name)
        result = cli.run(project=project, args=["artifact", "show", artifact_name])
        assert result.exit_code == 0


# Test configuration with cache storage-service and remote action cache for nested REAPI.
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_remote_apis_socket_with_cache_storage_service_and_action_cache(cli, tmpdir, datafiles):
    project = str(datafiles)
    element_name = "sandbox/remote-apis-socket.bst"

    with create_artifact_share(os.path.join(str(tmpdir), "remote")) as share:
        cli.configure(
            {
                "cache": {
                    "storage-service": {"url": share.repo},
                },
                "remote-execution": {
                    "action-cache-service": {"url": share.repo, "push": True},
                },
            }
        )

        result = cli.run(project=project, args=["build", element_name])
        assert result.exit_code == 0


# Test configuration with two different storage-services and remote action cache for nested REAPI.
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_remote_apis_socket_with_two_storage_services_and_action_cache(cli, tmpdir, datafiles):
    project = str(datafiles)
    element_name = "sandbox/remote-apis-socket.bst"

    with create_artifact_share(os.path.join(str(tmpdir), "remote1")) as share1, create_artifact_share(
        os.path.join(str(tmpdir), "remote2")
    ) as share2:
        cli.configure(
            {
                "cache": {
                    "storage-service": {"url": share1.repo},
                },
                "remote-execution": {
                    "storage-service": {"url": share2.repo},
                    "action-cache-service": {"url": share2.repo, "push": True},
                },
            }
        )

        result = cli.run(project=project, args=["build", element_name])
        assert result.exit_code == 0
