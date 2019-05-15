import multiprocessing
import os
import signal

import pytest

from buildstream import _yaml, _signals, utils
from buildstream._context import Context
from buildstream._project import Project
from buildstream._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from buildstream.testing import cli

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


def tree_maker(cas, tree, directory):
    if tree.root.ByteSize() == 0:
        tree.root.CopyFrom(directory)

    for directory_node in directory.directories:
        child_directory = tree.children.add()

        with open(cas.objpath(directory_node.digest), 'rb') as f:
            child_directory.ParseFromString(f.read())

        tree_maker(cas, tree, child_directory)


@pytest.mark.datafiles(DATA_DIR)
def test_pull(cli, tmpdir, datafiles):
    project_dir = str(datafiles)

    # Set up an artifact cache.
    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare')) as share:
        # Configure artifact share
        cache_dir = os.path.join(str(tmpdir), 'cache')
        user_config_file = str(tmpdir.join('buildstream.conf'))
        user_config = {
            'scheduler': {
                'pushers': 1
            },
            'artifacts': {
                'url': share.repo,
                'push': True,
            },
            'cachedir': cache_dir
        }

        # Write down the user configuration file
        _yaml.dump(_yaml.node_sanitize(user_config), filename=user_config_file)
        # Ensure CLI calls will use it
        cli.configure(user_config)

        # First build the project with the artifact cache configured
        result = cli.run(project=project_dir, args=['build', 'target.bst'])
        result.assert_success()

        # Assert that we are now cached locally
        assert cli.get_element_state(project_dir, 'target.bst') == 'cached'
        # Assert that we shared/pushed the cached artifact
        assert share.has_artifact(cli.get_artifact_name(project_dir, 'test', 'target.bst'))

        # Delete the artifact locally
        cli.remove_artifact_from_cache(project_dir, 'target.bst')

        # Assert that we are not cached locally anymore
        assert cli.get_element_state(project_dir, 'target.bst') != 'cached'

        # Fake minimal context
        context = Context()
        context.load(config=user_config_file)
        context.set_message_handler(message_handler)

        # Load the project
        project = Project(project_dir, context)
        project.ensure_fully_loaded()

        # Assert that the element's artifact is **not** cached
        element = project.load_elements(['target.bst'])[0]
        element_key = cli.get_element_key(project_dir, 'target.bst')
        assert not cli.artifact.is_cached(cache_dir, element, element_key)

        queue = multiprocessing.Queue()
        # Use subprocess to avoid creation of gRPC threads in main BuildStream process
        # See https://github.com/grpc/grpc/blob/master/doc/fork_support.md for details
        process = multiprocessing.Process(target=_queue_wrapper,
                                          args=(_test_pull, queue, user_config_file, project_dir,
                                                cache_dir, 'target.bst', element_key))

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
        assert cli.artifact.is_cached(cache_dir, element, element_key)


def _test_pull(user_config_file, project_dir, cache_dir,
               element_name, element_key, queue):
    # Fake minimal context
    context = Context()
    context.load(config=user_config_file)
    context.cachedir = cache_dir
    context.casdir = os.path.join(cache_dir, 'cas')
    context.tmpdir = os.path.join(cache_dir, 'tmp')
    context.set_message_handler(message_handler)

    # Load the project manually
    project = Project(project_dir, context)
    project.ensure_fully_loaded()

    # Create a local artifact cache handle
    artifactcache = context.artifactcache

    # Load the target element
    element = project.load_elements([element_name])[0]

    # Manually setup the CAS remote
    artifactcache.setup_remotes(use_config=True)

    if artifactcache.has_push_remotes(plugin=element):
        # Push the element's artifact
        if not artifactcache.pull(element, element_key):
            queue.put("Pull operation failed")
        else:
            queue.put(None)
    else:
        queue.put("No remote configured for element {}".format(element_name))


@pytest.mark.datafiles(DATA_DIR)
def test_pull_tree(cli, tmpdir, datafiles):
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
        # Ensure CLI calls will use it
        cli.configure(user_config)

        # First build the project with the artifact cache configured
        result = cli.run(project=project_dir, args=['build', 'target.bst'])
        result.assert_success()

        # Assert that we are now cached locally
        assert cli.get_element_state(project_dir, 'target.bst') == 'cached'
        # Assert that we shared/pushed the cached artifact
        assert share.has_artifact(cli.get_artifact_name(project_dir, 'test', 'target.bst'))

        # Fake minimal context
        context = Context()
        context.load(config=user_config_file)
        context.set_message_handler(message_handler)

        # Load the project and CAS cache
        project = Project(project_dir, context)
        project.ensure_fully_loaded()
        artifactcache = context.artifactcache
        cas = context.get_cascache()

        # Assert that the element's artifact is cached
        element = project.load_elements(['target.bst'])[0]
        element_key = cli.get_element_key(project_dir, 'target.bst')
        assert cli.artifact.is_cached(rootcache_dir, element, element_key)

        # Retrieve the Directory object from the cached artifact
        artifact_digest = cli.artifact.get_digest(rootcache_dir, element, element_key)

        queue = multiprocessing.Queue()
        # Use subprocess to avoid creation of gRPC threads in main BuildStream process
        # See https://github.com/grpc/grpc/blob/master/doc/fork_support.md for details
        process = multiprocessing.Process(target=_queue_wrapper,
                                          args=(_test_push_tree, queue, user_config_file, project_dir,
                                                artifact_digest))

        try:
            # Keep SIGINT blocked in the child process
            with _signals.blocked([signal.SIGINT], ignore=False):
                process.start()

            tree_hash, tree_size = queue.get()
            process.join()
        except KeyboardInterrupt:
            utils._kill_process_tree(process.pid)
            raise

        assert tree_hash and tree_size

        # Now delete the artifact locally
        cli.remove_artifact_from_cache(project_dir, 'target.bst')

        # Assert that we are not cached locally anymore
        assert cli.get_element_state(project_dir, 'target.bst') != 'cached'

        tree_digest = remote_execution_pb2.Digest(hash=tree_hash,
                                                  size_bytes=tree_size)

        queue = multiprocessing.Queue()
        # Use subprocess to avoid creation of gRPC threads in main BuildStream process
        process = multiprocessing.Process(target=_queue_wrapper,
                                          args=(_test_pull_tree, queue, user_config_file, project_dir,
                                                tree_digest))

        try:
            # Keep SIGINT blocked in the child process
            with _signals.blocked([signal.SIGINT], ignore=False):
                process.start()

            directory_hash, directory_size = queue.get()
            process.join()
        except KeyboardInterrupt:
            utils._kill_process_tree(process.pid)
            raise

        # Directory size now zero with AaaP and stack element commit #1cbc5e63dc
        assert directory_hash and not directory_size

        directory_digest = remote_execution_pb2.Digest(hash=directory_hash,
                                                       size_bytes=directory_size)

        # Ensure the entire Tree stucture has been pulled
        assert os.path.exists(cas.objpath(directory_digest))


def _test_push_tree(user_config_file, project_dir, artifact_digest, queue):
    # Fake minimal context
    context = Context()
    context.load(config=user_config_file)
    context.set_message_handler(message_handler)

    # Load the project manually
    project = Project(project_dir, context)
    project.ensure_fully_loaded()

    # Create a local artifact cache and cas handle
    artifactcache = context.artifactcache
    cas = context.get_cascache()

    # Manually setup the CAS remote
    artifactcache.setup_remotes(use_config=True)

    if artifactcache.has_push_remotes():
        directory = remote_execution_pb2.Directory()

        with open(cas.objpath(artifact_digest), 'rb') as f:
            directory.ParseFromString(f.read())

        # Build the Tree object while we are still cached
        tree = remote_execution_pb2.Tree()
        tree_maker(cas, tree, directory)

        # Push the Tree as a regular message
        tree_digest = artifactcache.push_message(project, tree)

        queue.put((tree_digest.hash, tree_digest.size_bytes))
    else:
        queue.put("No remote configured")


def _test_pull_tree(user_config_file, project_dir, artifact_digest, queue):
    # Fake minimal context
    context = Context()
    context.load(config=user_config_file)
    context.set_message_handler(message_handler)

    # Load the project manually
    project = Project(project_dir, context)
    project.ensure_fully_loaded()

    # Create a local artifact cache handle
    artifactcache = context.artifactcache

    # Manually setup the CAS remote
    artifactcache.setup_remotes(use_config=True)

    if artifactcache.has_push_remotes():
        # Pull the artifact using the Tree object
        directory_digest = artifactcache.pull_tree(project, artifact_digest)
        queue.put((directory_digest.hash, directory_digest.size_bytes))
    else:
        queue.put("No remote configured")
