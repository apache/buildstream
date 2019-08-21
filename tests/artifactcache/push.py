# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os

import pytest

from buildstream import _yaml, Scope
from buildstream._project import Project
from buildstream._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from buildstream.testing import cli  # pylint: disable=unused-import

from tests.testutils import create_artifact_share, dummy_context


# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


@pytest.mark.in_subprocess
@pytest.mark.datafiles(DATA_DIR)
def test_push(cli, tmpdir, datafiles):
    project_dir = str(datafiles)

    # First build the project without the artifact cache configured
    result = cli.run(project=project_dir, args=['build', 'target.bst'])
    result.assert_success()

    # Assert that we are now cached locally
    assert cli.get_element_state(project_dir, 'target.bst') == 'cached'

    # Set up an artifact cache.
    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare')) as share:
        # Configure artifact share
        rootcache_dir = os.path.join(str(tmpdir), 'cache')
        user_config_file = str(tmpdir.join('buildstream.conf'))
        user_config = {
            'scheduler': {
                'pushers': 1
            },
            'artifacts': {
                'url': share.repo,
                'push': True,
            },
            'cachedir': rootcache_dir
        }

        # Write down the user configuration file
        _yaml.roundtrip_dump(user_config, file=user_config_file)

        with dummy_context(config=user_config_file) as context:
            # Load the project manually
            project = Project(project_dir, context)
            project.ensure_fully_loaded()

            # Assert that the element's artifact is cached
            element = project.load_elements(['target.bst'])[0]
            element_key = cli.get_element_key(project_dir, 'target.bst')
            assert cli.artifact.is_cached(rootcache_dir, element, element_key)

            # Create a local artifact cache handle
            artifactcache = context.artifactcache

            # Ensure the element's artifact memeber is initialised
            # This is duplicated from Pipeline.resolve_elements()
            # as this test does not use the cli frontend.
            for e in element.dependencies(Scope.ALL):
                # Determine initial element state.
                e._update_state()

            # Manually setup the CAS remotes
            artifactcache.setup_remotes(use_config=True)
            artifactcache.initialize_remotes()

            assert artifactcache.has_push_remotes(plugin=element), \
                "No remote configured for element target.bst"
            assert element._push(), "Push operation failed"

        assert share.has_artifact(cli.get_artifact_name(project_dir, 'test', 'target.bst', cache_key=element_key))


@pytest.mark.in_subprocess
@pytest.mark.datafiles(DATA_DIR)
def test_push_message(tmpdir, datafiles):
    project_dir = str(datafiles)

    # Set up an artifact cache.
    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare')) as share:
        # Configure artifact share
        rootcache_dir = os.path.join(str(tmpdir), 'cache')
        user_config_file = str(tmpdir.join('buildstream.conf'))
        user_config = {
            'scheduler': {
                'pushers': 1
            },
            'artifacts': {
                'url': share.repo,
                'push': True,
            },
            'cachedir': rootcache_dir
        }

        # Write down the user configuration file
        _yaml.roundtrip_dump(user_config, file=user_config_file)

        with dummy_context(config=user_config_file) as context:
            # Load the project manually
            project = Project(project_dir, context)
            project.ensure_fully_loaded()

            # Create a local artifact cache handle
            artifactcache = context.artifactcache

            # Manually setup the artifact remote
            artifactcache.setup_remotes(use_config=True)
            artifactcache.initialize_remotes()
            assert artifactcache.has_push_remotes()

            command = remote_execution_pb2.Command(arguments=['/usr/bin/gcc', '--help'],
                                                   working_directory='/buildstream-build',
                                                   output_directories=['/buildstream-install'])

            # Push the message object
            command_digest = artifactcache.push_message(project, command)
            message_hash, message_size = command_digest.hash, command_digest.size_bytes

        assert message_hash and message_size
        message_digest = remote_execution_pb2.Digest(hash=message_hash,
                                                     size_bytes=message_size)
        assert share.has_object(message_digest)
