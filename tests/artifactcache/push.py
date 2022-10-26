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

from buildstream import _yaml
from buildstream._project import Project
from buildstream._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from buildstream._testing import cli  # pylint: disable=unused-import

from tests.testutils import create_artifact_share, create_split_share, dummy_context


# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


# Push the given element and return its artifact key for assertions.
def _push(cli, cache_dir, project_dir, config_file, target):
    with dummy_context(config=config_file) as context:
        # Load the project manually
        project = Project(project_dir, context)
        project.ensure_fully_loaded()

        # Assert that the element's artifact is cached
        element = project.load_elements(["target.bst"])[0]
        element_key = cli.get_element_key(project_dir, "target.bst")
        assert cli.artifact.is_cached(cache_dir, element, element_key)

        # Create a local artifact cache handle
        artifactcache = context.artifactcache

        # Initialize remotes
        context.initialize_remotes(True, True, None, None)

        # Query local cache
        element._load_artifact(pull=False)

        assert artifactcache.has_push_remotes(plugin=element), "No remote configured for element target.bst"
        assert element._push(), "Push operation failed"

    return element_key


@pytest.mark.datafiles(DATA_DIR)
def test_push(cli, tmpdir, datafiles):
    project_dir = str(datafiles)

    # First build the project without the artifact cache configured
    result = cli.run(project=project_dir, args=["build", "target.bst"])
    result.assert_success()

    # Assert that we are now cached locally
    assert cli.get_element_state(project_dir, "target.bst") == "cached"

    # Set up an artifact cache.
    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:
        # Configure artifact share
        rootcache_dir = os.path.join(str(tmpdir), "cache")
        user_config_file = str(tmpdir.join("buildstream.conf"))
        user_config = {
            "scheduler": {"pushers": 1},
            "artifacts": {
                "servers": [
                    {
                        "url": share.repo,
                        "push": True,
                    }
                ]
            },
            "cachedir": rootcache_dir,
        }

        # Write down the user configuration file
        _yaml.roundtrip_dump(user_config, file=user_config_file)
        element_key = _push(cli, rootcache_dir, project_dir, user_config_file, "target.bst")
        assert share.get_artifact(cli.get_artifact_name(project_dir, "test", "target.bst", cache_key=element_key))


@pytest.mark.datafiles(DATA_DIR)
def test_push_split(cli, tmpdir, datafiles):
    project_dir = str(datafiles)

    # First build the project without the artifact cache configured
    result = cli.run(project=project_dir, args=["build", "target.bst"])
    result.assert_success()

    # Assert that we are now cached locally
    assert cli.get_element_state(project_dir, "target.bst") == "cached"

    indexshare = os.path.join(str(tmpdir), "indexshare")
    storageshare = os.path.join(str(tmpdir), "storageshare")

    # Set up an artifact cache.
    with create_split_share(indexshare, storageshare) as (index, storage):
        rootcache_dir = os.path.join(str(tmpdir), "cache")
        user_config = {
            "scheduler": {"pushers": 1},
            "artifacts": {
                "servers": [
                    {"url": index.repo, "push": True, "type": "index"},
                    {"url": storage.repo, "push": True, "type": "storage"},
                ],
            },
            "cachedir": rootcache_dir,
        }
        config_path = str(tmpdir.join("buildstream.conf"))
        _yaml.roundtrip_dump(user_config, file=config_path)

        element_key = _push(cli, rootcache_dir, project_dir, config_path, "target.bst")
        proto = index.get_artifact_proto(
            cli.get_artifact_name(project_dir, "test", "target.bst", cache_key=element_key)
        )
        assert storage.get_cas_files(proto) is not None


@pytest.mark.datafiles(DATA_DIR)
def test_push_message(tmpdir, datafiles):
    project_dir = str(datafiles)

    # Set up an artifact cache.
    artifactshare = os.path.join(str(tmpdir), "artifactshare")
    with create_artifact_share(artifactshare) as share:
        # Configure artifact share
        rootcache_dir = os.path.join(str(tmpdir), "cache")
        user_config_file = str(tmpdir.join("buildstream.conf"))
        user_config = {
            "scheduler": {"pushers": 1},
            "artifacts": {
                "servers": [
                    {
                        "url": share.repo,
                        "push": True,
                    }
                ]
            },
            "cachedir": rootcache_dir,
        }

        # Write down the user configuration file
        _yaml.roundtrip_dump(user_config, file=user_config_file)

        with dummy_context(config=user_config_file) as context:
            # Load the project manually
            project = Project(project_dir, context)
            project.ensure_fully_loaded()

            # Create a local artifact cache handle
            artifactcache = context.artifactcache

            # Initialize remotes
            context.initialize_remotes(True, True, None, None)
            assert artifactcache.has_push_remotes()

            command = remote_execution_pb2.Command(
                arguments=["/usr/bin/gcc", "--help"],
                working_directory="/buildstream-build",
                output_directories=["/buildstream-install"],
            )

            # Push the message object
            _, remotes = artifactcache.get_remotes(project.name, True)
            assert len(remotes) == 1
            command_digest = remotes[0].push_message(command)
            message_hash, message_size = command_digest.hash, command_digest.size_bytes

        assert message_hash and message_size
        message_digest = remote_execution_pb2.Digest(hash=message_hash, size_bytes=message_size)
        assert share.has_object(message_digest)
