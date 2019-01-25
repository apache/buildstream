import string
import pytest
import subprocess
import os
import shutil
import signal
from collections import namedtuple

from contextlib import contextmanager
from multiprocessing import Process, Queue
import pytest_cov

from buildstream import _yaml
from buildstream._cas import CASCache
from buildstream._cas.casserver import create_server
from buildstream._exceptions import CASError
from buildstream._protos.build.bazel.remote.execution.v2 import remote_execution_pb2


# ArtifactShare()
#
# Abstract class providing scaffolding for
# generating data to be used with various sources
#
# Args:
#    directory (str): The base temp directory for the test
#    total_space (int): Mock total disk space on artifact server
#    free_space (int): Mock free disk space on artifact server
#
class ArtifactShare():

    def __init__(self, directory, *,
                 total_space=None,
                 free_space=None,
                 min_head_size=int(2e9),
                 max_head_size=int(10e9)):

        # The working directory for the artifact share (in case it
        # needs to do something outside of its backend's storage folder).
        #
        self.directory = os.path.abspath(directory)

        # The directory the actual repo will be stored in.
        #
        # Unless this gets more complicated, just use this directly
        # in tests as a remote artifact push/pull configuration
        #
        self.repodir = os.path.join(self.directory, 'repo')
        os.makedirs(self.repodir)

        self.cas = CASCache(self.repodir)

        self.total_space = total_space
        self.free_space = free_space

        self.max_head_size = max_head_size
        self.min_head_size = min_head_size

        q = Queue()

        self.process = Process(target=self.run, args=(q,))
        self.process.start()

        # Retrieve port from server subprocess
        port = q.get()

        self.repo = 'http://localhost:{}'.format(port)

    # run():
    #
    # Run the artifact server.
    #
    def run(self, q):
        pytest_cov.embed.cleanup_on_sigterm()

        try:
            # Optionally mock statvfs
            if self.total_space:
                if self.free_space is None:
                    self.free_space = self.total_space
                os.statvfs = self._mock_statvfs

            server = create_server(self.repodir,
                                   max_head_size=self.max_head_size,
                                   min_head_size=self.min_head_size,
                                   enable_push=True)
            port = server.add_insecure_port('localhost:0')

            server.start()

            # Send port to parent
            q.put(port)

        except Exception as e:
            q.put(None)
            raise

        # Sleep until termination by signal
        signal.pause()

    # has_object():
    #
    # Checks whether the object is present in the share
    #
    # Args:
    #    digest (str): The object's digest
    #
    # Returns:
    #    (bool): True if the object exists in the share, otherwise false.
    def has_object(self, digest):

        assert isinstance(digest, remote_execution_pb2.Digest)

        object_path = self.cas.objpath(digest)

        return os.path.exists(object_path)

    # has_artifact():
    #
    # Checks whether the artifact is present in the share
    #
    # Args:
    #    project_name (str): The project name
    #    element_name (str): The element name
    #    cache_key (str): The cache key
    #
    # Returns:
    #    (str): artifact digest if the artifact exists in the share, otherwise None.
    def has_artifact(self, project_name, element_name, cache_key):

        # NOTE: This should be kept in line with our
        #       artifact cache code, the below is the
        #       same algo for creating an artifact reference
        #

        # Replace path separator and chop off the .bst suffix
        element_name = os.path.splitext(element_name.replace(os.sep, '-'))[0]

        valid_chars = string.digits + string.ascii_letters + '-._'
        element_name = ''.join([
            x if x in valid_chars else '_'
            for x in element_name
        ])
        artifact_key = '{0}/{1}/{2}'.format(project_name, element_name, cache_key)

        try:
            tree = self.cas.resolve_ref(artifact_key)
            reachable = set()
            try:
                self.cas._reachable_refs_dir(reachable, tree, update_mtime=False)
            except FileNotFoundError:
                return None
            for digest in reachable:
                object_name = os.path.join(self.cas.casdir, 'objects', digest[:2], digest[2:])
                if not os.path.exists(object_name):
                    return None
            return tree
        except CASError:
            return None

    # close():
    #
    # Remove the artifact share.
    #
    def close(self):
        self.process.terminate()
        self.process.join()

        shutil.rmtree(self.directory)

    def _mock_statvfs(self, path):
        repo_size = 0
        for root, _, files in os.walk(self.repodir):
            for filename in files:
                repo_size += os.path.getsize(os.path.join(root, filename))

        return statvfs_result(f_blocks=self.total_space,
                              f_bfree=self.free_space - repo_size,
                              f_bavail=self.free_space - repo_size,
                              f_bsize=1)


# create_artifact_share()
#
# Create an ArtifactShare for use in a test case
#
@contextmanager
def create_artifact_share(directory, *, total_space=None, free_space=None,
                          min_head_size=int(2e9),
                          max_head_size=int(10e9)):
    share = ArtifactShare(directory, total_space=total_space, free_space=free_space,
                          min_head_size=min_head_size, max_head_size=max_head_size)
    try:
        yield share
    finally:
        share.close()


statvfs_result = namedtuple('statvfs_result', 'f_blocks f_bfree f_bsize f_bavail')
