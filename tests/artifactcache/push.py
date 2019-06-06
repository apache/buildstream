# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import multiprocessing
import os
import signal

import pytest

from buildstream import _yaml, _signals, utils, Scope
from buildstream._context import Context
from buildstream._project import Project
from buildstream._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from buildstream.testing import cli  # pylint: disable=unused-import
from tests.testutils import create_artifact_share


# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


# Handle messages from the pipeline
def message_handler(message, context):
    pass


# Since parent processes wait for queue events, we need
# to put something on it if the called process raises an
# exception.
def _queue_wrapper(target, queue, *args):
    try:
        target(*args, queue=queue)
    except Exception as e:
        queue.put(str(e))
        raise


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
        _yaml.dump(_yaml.node_sanitize(user_config), filename=user_config_file)

        # Fake minimal context
        context = Context()
        context.load(config=user_config_file)
        context.set_message_handler(message_handler)

        # Load the project manually
        project = Project(project_dir, context)
        project.ensure_fully_loaded()

        # Assert that the element's artifact is cached
        element = project.load_elements(['target.bst'])[0]
        element_key = cli.get_element_key(project_dir, 'target.bst')
        assert cli.artifact.is_cached(rootcache_dir, element, element_key)

        queue = multiprocessing.Queue()
        # Use subprocess to avoid creation of gRPC threads in main BuildStream process
        # See https://github.com/grpc/grpc/blob/master/doc/fork_support.md for details
        process = multiprocessing.Process(target=_queue_wrapper,
                                          args=(_test_push, queue, user_config_file, project_dir,
                                                'target.bst'))

        try:
            # Keep SIGINT blocked in the child process
            with _signals.blocked([signal.SIGINT], ignore=False):
                process.start()

            error = queue.get()
            process.join()
        except KeyboardInterrupt:
            utils._kill_process_tree(process.pid)
            raise

        assert not error
        assert share.has_artifact(cli.get_artifact_name(project_dir, 'test', 'target.bst', cache_key=element_key))


def _test_push(user_config_file, project_dir, element_name, queue):
    # Fake minimal context
    context = Context()
    context.load(config=user_config_file)
    context.set_message_handler(message_handler)

    # Load the project manually
    project = Project(project_dir, context)
    project.ensure_fully_loaded()

    # Create a local artifact cache handle
    artifactcache = context.artifactcache

    # Load the target element
    element = project.load_elements([element_name])[0]

    # Ensure the element's artifact memeber is initialised
    # This is duplicated from Pipeline.resolve_elements()
    # as this test does not use the cli frontend.
    for e in element.dependencies(Scope.ALL):
        # Preflight
        e._preflight()
        # Determine initial element state.
        e._update_state()

    # Manually setup the CAS remotes
    artifactcache.setup_remotes(use_config=True)
    artifactcache.initialize_remotes()

    if artifactcache.has_push_remotes(plugin=element):
        # Push the element's artifact
        if not element._push():
            queue.put("Push operation failed")
        else:
            queue.put(None)
    else:
        queue.put("No remote configured for element {}".format(element_name))


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
        _yaml.dump(_yaml.node_sanitize(user_config), filename=user_config_file)

        queue = multiprocessing.Queue()
        # Use subprocess to avoid creation of gRPC threads in main BuildStream process
        # See https://github.com/grpc/grpc/blob/master/doc/fork_support.md for details
        process = multiprocessing.Process(target=_queue_wrapper,
                                          args=(_test_push_message, queue, user_config_file,
                                                project_dir))

        try:
            # Keep SIGINT blocked in the child process
            with _signals.blocked([signal.SIGINT], ignore=False):
                process.start()

            message_hash, message_size = queue.get()
            process.join()
        except KeyboardInterrupt:
            utils._kill_process_tree(process.pid)
            raise

        assert message_hash and message_size
        message_digest = remote_execution_pb2.Digest(hash=message_hash,
                                                     size_bytes=message_size)
        assert share.has_object(message_digest)


def _test_push_message(user_config_file, project_dir, queue):
    # Fake minimal context
    context = Context()
    context.load(config=user_config_file)
    context.set_message_handler(message_handler)

    # Load the project manually
    project = Project(project_dir, context)
    project.ensure_fully_loaded()

    # Create a local artifact cache handle
    artifactcache = context.artifactcache

    # Manually setup the artifact remote
    artifactcache.setup_remotes(use_config=True)
    artifactcache.initialize_remotes()

    if artifactcache.has_push_remotes():
        # Create an example message object
        command = remote_execution_pb2.Command(arguments=['/usr/bin/gcc', '--help'],
                                               working_directory='/buildstream-build',
                                               output_directories=['/buildstream-install'])

        # Push the message object
        command_digest = artifactcache.push_message(project, command)

        queue.put((command_digest.hash, command_digest.size_bytes))
    else:
        queue.put("No remote configured")
