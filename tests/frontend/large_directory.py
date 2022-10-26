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

from contextlib import contextmanager
import os
import pytest

import grpc

from buildstream._testing import cli  # pylint: disable=unused-import
from tests.testutils import create_artifact_share, assert_shared


# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


@contextmanager
def limit_grpc_message_length(limit):
    orig_insecure_channel = grpc.insecure_channel

    def new_insecure_channel(target):
        return orig_insecure_channel(target, options=(("grpc.max_send_message_length", limit),))

    grpc.insecure_channel = new_insecure_channel
    try:
        yield
    finally:
        grpc.insecure_channel = orig_insecure_channel


@pytest.mark.datafiles(DATA_DIR)
def test_large_directory(cli, tmpdir, datafiles):
    project = str(datafiles)

    # Number of files chosen to ensure the complete list of digests exceeds
    # our 1 MB gRPC message limit. I.e., test message splitting.
    MAX_MESSAGE_LENGTH = 1024 * 1024
    NUM_FILES = MAX_MESSAGE_LENGTH // 64 + 1

    large_directory_dir = os.path.join(project, "files", "large-directory")
    os.mkdir(large_directory_dir)
    for i in range(NUM_FILES):
        with open(os.path.join(large_directory_dir, str(i)), "w", encoding="utf-8") as f:
            # The files need to have different content as we want different digests.
            f.write(str(i))

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:
        # Configure bst to push to the artifact share
        cli.configure(
            {
                "artifacts": {
                    "servers": [
                        {"url": share.repo, "push": True},
                    ]
                }
            }
        )

        # Enforce 1 MB gRPC message limit
        with limit_grpc_message_length(MAX_MESSAGE_LENGTH):
            # Build and push
            result = cli.run(project=project, args=["build", "import-large-directory.bst"])
            result.assert_success()

        # Assert that we are now cached locally
        assert cli.get_element_state(project, "import-large-directory.bst") == "cached"

        # Assert that the push was successful
        assert_shared(cli, share, project, "import-large-directory.bst")
