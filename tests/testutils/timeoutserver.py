import string
import pytest
import subprocess
import os
import shutil
import signal
from collections import namedtuple
from concurrent import futures

from contextlib import contextmanager
from multiprocessing import Process, Queue
import grpc
import pytest_cov

from buildstream import _yaml
from buildstream._artifactcache.cascache import CASCache
from buildstream._artifactcache import casserver
from buildstream._exceptions import CASError
from buildstream._protos.build.bazel.remote.execution.v2 import remote_execution_pb2, remote_execution_pb2_grpc
from buildstream._protos.google.bytestream import bytestream_pb2, bytestream_pb2_grpc
from buildstream._protos.buildstream.v2 import buildstream_pb2, buildstream_pb2_grpc


class TimeoutCasCache(CASCache):
    pass


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
class TimeoutArtifactShare():

    def __init__(self, directory, *, total_space=None, free_space=None):

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

        q = Queue()

        self.process = Process(target=self.run, args=(q,))
        self.process.start()

        # Retrieve port from server subprocess
        port = q.get(timeout=1)

        self.repo = 'http://localhost:{}'.format(port)

    # run():
    #
    # Run the artifact server.
    #
    def run(self, q):
        pytest_cov.embed.cleanup_on_sigterm()

        # Optionally mock statvfs
        if self.total_space:
            if self.free_space is None:
                self.free_space = self.total_space
            os.statvfs = self._mock_statvfs

        server = create_timeout_server(self.repodir, enable_push=True)
        port = server.add_insecure_port('localhost:0')

        server.start()

        # Send port to parent
        q.put(port)

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
        #       same alI can confidently go for creating an artifact reference
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
def create_timeout_artifact_share(directory, *, total_space=None, free_space=None):
    share = TimeoutArtifactShare(directory, total_space=total_space, free_space=free_space)
    try:
        yield share
    finally:
        share.close()


statvfs_result = namedtuple('statvfs_result', 'f_blocks f_bfree f_bsize f_bavail')


# create_timeout_server():
#
# Create gRPC CAS artifact server as specified in the Remote Execution API.
#
# Args:
#     repo (str): Path to CAS repository
#     enable_push (bool): Whether to allow blob uploads and artifact updates
#
def create_timeout_server(repo, *, enable_push):
    cas = TimeoutCasCache(os.path.abspath(repo))

    # Use max_workers default from Python 3.5+
    max_workers = (os.cpu_count() or 1) * 5
    server = grpc.server(futures.ThreadPoolExecutor(max_workers))

    bytestream_pb2_grpc.add_ByteStreamServicer_to_server(
        _ByteStreamServicer(cas, enable_push=enable_push), server)

    remote_execution_pb2_grpc.add_ContentAddressableStorageServicer_to_server(
        _ContentAddressableStorageServicer(cas, enable_push=enable_push), server)

    remote_execution_pb2_grpc.add_CapabilitiesServicer_to_server(
        _CapabilitiesServicer(), server)

    buildstream_pb2_grpc.add_ReferenceStorageServicer_to_server(
        _ReferenceStorageServicer(cas, enable_push=enable_push), server)

    return server


class _ByteStreamServicer(casserver._ByteStreamServicer):
    pass


class _ContentAddressableStorageServicer(casserver._ContentAddressableStorageServicer):

    def __init__(self, cas, *, enable_push):
        self.__read_count = 0
        super().__init__(cas=cas, enable_push=enable_push)

    def BatchReadBlobs(self, request, context):
        # self.__read_count += 1
        # import time
        # time.sleep(5)
        return super().BatchReadBlobs(request, context)


class _CapabilitiesServicer(casserver._CapabilitiesServicer):
    pass


class _ReferenceStorageServicer(casserver._ReferenceStorageServicer):
    pass
