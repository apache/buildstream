import multiprocessing
import os
import signal

import pytest

from pluginbase import PluginBase
from buildstream import _yaml, _signals, utils
from buildstream._context import Context
from buildstream._project import Project
from buildstream._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from buildstream.storage._casbaseddirectory import CasBasedDirectory

from tests.testutils import cli, create_artifact_share


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
        artifact_dir = os.path.join(str(tmpdir), 'cache', 'artifacts')
        user_config_file = str(tmpdir.join('buildstream.conf'))
        user_config = {
            'scheduler': {
                'pushers': 1
            },
            'artifacts': {
                'url': share.repo,
                'push': True,
            }
        }

        # Write down the user configuration file
        _yaml.dump(_yaml.node_sanitize(user_config), filename=user_config_file)

        # Fake minimal context
        context = Context()
        context.load(config=user_config_file)
        context.artifactdir = artifact_dir
        context.set_message_handler(message_handler)

        # Load the project manually
        project = Project(project_dir, context)
        project.ensure_fully_loaded()

        # Create a local CAS cache handle
        cas = context.artifactcache

        # Assert that the element's artifact is cached
        element = project.load_elements(['target.bst'])[0]
        element_key = cli.get_element_key(project_dir, 'target.bst')
        assert cas.contains(element, element_key)

        queue = multiprocessing.Queue()
        # Use subprocess to avoid creation of gRPC threads in main BuildStream process
        # See https://github.com/grpc/grpc/blob/master/doc/fork_support.md for details
        process = multiprocessing.Process(target=_queue_wrapper,
                                          args=(_test_push, queue, user_config_file, project_dir,
                                                artifact_dir, 'target.bst', element_key))

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
        assert share.has_artifact('test', 'target.bst', element_key)


def _test_push(user_config_file, project_dir, artifact_dir,
               element_name, element_key, queue):
    # Fake minimal context
    context = Context()
    context.load(config=user_config_file)
    context.artifactdir = artifact_dir
    context.set_message_handler(message_handler)

    # Load the project manually
    project = Project(project_dir, context)
    project.ensure_fully_loaded()

    # Create a local CAS cache handle
    cas = context.artifactcache

    # Load the target element
    element = project.load_elements([element_name])[0]

    # Manually setup the CAS remote
    cas.setup_remotes(use_config=True)
    cas.initialize_remotes()

    if cas.has_push_remotes(element=element):
        # Push the element's artifact
        if not cas.push(element, [element_key]):
            queue.put("Push operation failed")
        else:
            queue.put(None)
    else:
        queue.put("No remote configured for element {}".format(element_name))


@pytest.mark.datafiles(DATA_DIR)
def test_push_directory(cli, tmpdir, datafiles):
    project_dir = str(datafiles)

    # First build the project without the artifact cache configured
    result = cli.run(project=project_dir, args=['build', 'target.bst'])
    result.assert_success()

    # Assert that we are now cached locally
    assert cli.get_element_state(project_dir, 'target.bst') == 'cached'

    # Set up an artifact cache.
    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare')) as share:
        # Configure artifact share
        artifact_dir = os.path.join(str(tmpdir), 'cache', 'artifacts')
        user_config_file = str(tmpdir.join('buildstream.conf'))
        user_config = {
            'scheduler': {
                'pushers': 1
            },
            'artifacts': {
                'url': share.repo,
                'push': True,
            }
        }

        # Write down the user configuration file
        _yaml.dump(_yaml.node_sanitize(user_config), filename=user_config_file)

        # Fake minimal context
        context = Context()
        context.load(config=user_config_file)
        context.artifactdir = os.path.join(str(tmpdir), 'cache', 'artifacts')
        context.set_message_handler(message_handler)

        # Load the project and CAS cache
        project = Project(project_dir, context)
        project.ensure_fully_loaded()
        artifactcache = context.artifactcache
        cas = artifactcache.cas

        # Assert that the element's artifact is cached
        element = project.load_elements(['target.bst'])[0]
        element_key = cli.get_element_key(project_dir, 'target.bst')
        assert artifactcache.contains(element, element_key)

        # Manually setup the CAS remote
        artifactcache.setup_remotes(use_config=True)
        artifactcache.initialize_remotes()
        assert artifactcache.has_push_remotes(element=element)

        # Recreate the CasBasedDirectory object from the cached artifact
        artifact_ref = artifactcache.get_artifact_fullname(element, element_key)
        artifact_digest = cas.resolve_ref(artifact_ref)

        queue = multiprocessing.Queue()
        # Use subprocess to avoid creation of gRPC threads in main BuildStream process
        # See https://github.com/grpc/grpc/blob/master/doc/fork_support.md for details
        process = multiprocessing.Process(target=_queue_wrapper,
                                          args=(_test_push_directory, queue, user_config_file,
                                                project_dir, artifact_dir, artifact_digest))

        try:
            # Keep SIGINT blocked in the child process
            with _signals.blocked([signal.SIGINT], ignore=False):
                process.start()

            directory_hash = queue.get()
            process.join()
        except KeyboardInterrupt:
            utils._kill_process_tree(process.pid)
            raise

        assert directory_hash
        assert artifact_digest.hash == directory_hash
        assert share.has_object(artifact_digest)


def _test_push_directory(user_config_file, project_dir, artifact_dir, artifact_digest, queue):
    # Fake minimal context
    context = Context()
    context.load(config=user_config_file)
    context.artifactdir = artifact_dir
    context.set_message_handler(message_handler)

    # Load the project manually
    project = Project(project_dir, context)
    project.ensure_fully_loaded()

    # Create a local CAS cache handle
    cas = context.artifactcache

    # Manually setup the CAS remote
    cas.setup_remotes(use_config=True)
    cas.initialize_remotes()

    if cas.has_push_remotes():
        # Create a CasBasedDirectory from local CAS cache content
        directory = CasBasedDirectory(context.artifactcache.cas, ref=artifact_digest)

        # Push the CasBasedDirectory object
        cas.push_directory(project, directory)

        queue.put(directory.ref.hash)
    else:
        queue.put("No remote configured")


@pytest.mark.datafiles(DATA_DIR)
def test_push_message(cli, tmpdir, datafiles):
    project_dir = str(datafiles)

    # Set up an artifact cache.
    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare')) as share:
        # Configure artifact share
        artifact_dir = os.path.join(str(tmpdir), 'cache', 'artifacts')
        user_config_file = str(tmpdir.join('buildstream.conf'))
        user_config = {
            'scheduler': {
                'pushers': 1
            },
            'artifacts': {
                'url': share.repo,
                'push': True,
            }
        }

        # Write down the user configuration file
        _yaml.dump(_yaml.node_sanitize(user_config), filename=user_config_file)

        queue = multiprocessing.Queue()
        # Use subprocess to avoid creation of gRPC threads in main BuildStream process
        # See https://github.com/grpc/grpc/blob/master/doc/fork_support.md for details
        process = multiprocessing.Process(target=_queue_wrapper,
                                          args=(_test_push_message, queue, user_config_file,
                                                project_dir, artifact_dir))

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


def _test_push_message(user_config_file, project_dir, artifact_dir, queue):
    # Fake minimal context
    context = Context()
    context.load(config=user_config_file)
    context.artifactdir = artifact_dir
    context.set_message_handler(message_handler)

    # Load the project manually
    project = Project(project_dir, context)
    project.ensure_fully_loaded()

    # Create a local CAS cache handle
    cas = context.artifactcache

    # Manually setup the CAS remote
    cas.setup_remotes(use_config=True)
    cas.initialize_remotes()

    if cas.has_push_remotes():
        # Create an example message object
        command = remote_execution_pb2.Command(arguments=['/usr/bin/gcc', '--help'],
                                               working_directory='/buildstream-build',
                                               output_directories=['/buildstream-install'])

        # Push the message object
        command_digest = cas.push_message(project, command)

        queue.put((command_digest.hash, command_digest.size_bytes))
    else:
        queue.put("No remote configured")
