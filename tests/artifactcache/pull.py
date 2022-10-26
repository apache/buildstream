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

from tests.testutils import create_artifact_share, dummy_context


# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


def tree_maker(cas, tree, directory):
    if tree.root.ByteSize() == 0:
        tree.root.CopyFrom(directory)

    for directory_node in directory.directories:
        child_directory = tree.children.add()

        with open(cas.objpath(directory_node.digest), "rb") as f:
            child_directory.ParseFromString(f.read())

        tree_maker(cas, tree, child_directory)


@pytest.mark.datafiles(DATA_DIR)
def test_pull(cli, tmpdir, datafiles):
    project_dir = str(datafiles)

    # Set up an artifact cache.
    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:
        # Configure artifact share
        cache_dir = os.path.join(str(tmpdir), "cache")
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
            "cachedir": cache_dir,
        }

        # Write down the user configuration file
        _yaml.roundtrip_dump(user_config, file=user_config_file)
        # Ensure CLI calls will use it
        cli.configure(user_config)

        # First build the project with the artifact cache configured
        result = cli.run(project=project_dir, args=["build", "target.bst"])
        result.assert_success()

        # Assert that we are now cached locally
        assert cli.get_element_state(project_dir, "target.bst") == "cached"
        # Assert that we shared/pushed the cached artifact
        assert share.get_artifact(cli.get_artifact_name(project_dir, "test", "target.bst"))

        # Delete the artifact locally
        cli.remove_artifact_from_cache(project_dir, "target.bst")

        # Assert that we are not cached locally anymore
        assert cli.get_element_state(project_dir, "target.bst") != "cached"

        with dummy_context(config=user_config_file) as context:
            # Load the project
            project = Project(project_dir, context)
            project.ensure_fully_loaded()

            # Assert that the element's artifact is **not** cached
            element = project.load_elements(["target.bst"])[0]
            element_key = cli.get_element_key(project_dir, "target.bst")
            assert not cli.artifact.is_cached(cache_dir, element, element_key)

            context.cachedir = cache_dir
            context.casdir = os.path.join(cache_dir, "cas")
            context.tmpdir = os.path.join(cache_dir, "tmp")

            # Load the project manually
            project = Project(project_dir, context)
            project.ensure_fully_loaded()

            # Create a local artifact cache handle
            artifactcache = context.artifactcache

            # Initialize remotes
            context.initialize_remotes(True, True, None, None)

            assert artifactcache.has_push_remotes(plugin=element), "No remote configured for element target.bst"
            assert artifactcache.pull(element, element_key), "Pull operation failed"

            assert cli.artifact.is_cached(cache_dir, element, element_key)


@pytest.mark.datafiles(DATA_DIR)
def test_pull_tree(cli, tmpdir, datafiles):
    project_dir = str(datafiles)

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
        # Ensure CLI calls will use it
        cli.configure(user_config)

        # First build the project with the artifact cache configured
        result = cli.run(project=project_dir, args=["build", "target.bst"])
        result.assert_success()

        # Assert that we are now cached locally
        assert cli.get_element_state(project_dir, "target.bst") == "cached"
        # Assert that we shared/pushed the cached artifact
        assert share.get_artifact(cli.get_artifact_name(project_dir, "test", "target.bst"))

        with dummy_context(config=user_config_file) as context:
            # Load the project and CAS cache
            project = Project(project_dir, context)
            project.ensure_fully_loaded()
            cas = context.get_cascache()

            # Assert that the element's artifact is cached
            element = project.load_elements(["target.bst"])[0]
            element_key = cli.get_element_key(project_dir, "target.bst")
            assert cli.artifact.is_cached(rootcache_dir, element, element_key)

            # Retrieve the Directory object from the cached artifact
            artifact_digest = cli.artifact.get_digest(rootcache_dir, element, element_key)

            # Initialize remotes
            context.initialize_remotes(True, True, None, None)

            artifactcache = context.artifactcache
            assert artifactcache.has_push_remotes()

            directory = remote_execution_pb2.Directory()

            with open(cas.objpath(artifact_digest), "rb") as f:
                directory.ParseFromString(f.read())

            # Build the Tree object while we are still cached
            tree = remote_execution_pb2.Tree()
            tree_maker(cas, tree, directory)

            # Push the Tree as a regular message
            _, remotes = artifactcache.get_remotes(project.name, True)
            assert len(remotes) == 1
            tree_digest = remotes[0].push_message(tree)
            tree_hash, tree_size = tree_digest.hash, tree_digest.size_bytes
            assert tree_hash and tree_size

            # Now delete the artifact locally
            cli.remove_artifact_from_cache(project_dir, "target.bst")

            # Assert that we are not cached locally anymore
            artifactcache.release_resources()
            cas._casd_channel.request_shutdown()
            cas.close_grpc_channels()
            assert cli.get_element_state(project_dir, "target.bst") != "cached"

            tree_digest = remote_execution_pb2.Digest(hash=tree_hash, size_bytes=tree_size)

            # Pull the artifact using the Tree object
            _, remotes = artifactcache.get_remotes(project.name, False)
            assert len(remotes) == 1
            directory_digest = cas.pull_tree(remotes[0], tree_digest)
            directory_hash, directory_size = directory_digest.hash, directory_digest.size_bytes

        # Directory size now zero with AaaP and stack element commit #1cbc5e63dc
        assert directory_hash and not directory_size

        directory_digest = remote_execution_pb2.Digest(hash=directory_hash, size_bytes=directory_size)

        # Ensure the entire Tree stucture has been pulled
        assert os.path.exists(cas.objpath(directory_digest))
