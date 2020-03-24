import os
import shutil
import signal
import sys
from collections import namedtuple
from contextlib import ExitStack, contextmanager
from concurrent import futures
from multiprocessing import Process, Queue

import grpc

from buildstream._cas import CASCache
from buildstream._cas.casserver import create_server
from buildstream._exceptions import CASError
from buildstream._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from buildstream._protos.buildstream.v2 import artifact_pb2, source_pb2


class BaseArtifactShare:
    def __init__(self):
        q = Queue()

        self.process = Process(target=self.run, args=(q,))
        self.process.start()

        # Retrieve port from server subprocess
        port = q.get()

        if port is None:
            raise Exception("Error occurred when starting artifact server.")

        self.repo = "http://localhost:{}".format(port)

    # run():
    #
    # Run the artifact server.
    #
    def run(self, q):
        with ExitStack() as stack:
            try:
                # Handle SIGTERM by calling sys.exit(0), which will raise a SystemExit exception,
                # properly executing cleanup code in `finally` clauses and context managers.
                # This is required to terminate buildbox-casd on SIGTERM.
                signal.signal(signal.SIGTERM, lambda signalnum, frame: sys.exit(0))

                try:
                    from pytest_cov.embed import cleanup_on_sigterm
                except ImportError:
                    pass
                else:
                    cleanup_on_sigterm()

                server = stack.enter_context(self._create_server())
                port = server.add_insecure_port("localhost:0")
                server.start()
            except Exception:
                q.put(None)
                raise

            # Send port to parent
            q.put(port)

            # Sleep until termination by signal
            signal.pause()

    # _create_server()
    #
    # Create the server that will be run in the process
    #
    def _create_server(self):
        raise NotImplementedError()

    # close():
    #
    # Remove the artifact share.
    #
    def close(self):
        self.process.terminate()
        self.process.join()


# DummyArtifactShare()
#
# A dummy artifact share without any capabilities
#
class DummyArtifactShare(BaseArtifactShare):
    @contextmanager
    def _create_server(self):
        max_workers = (os.cpu_count() or 1) * 5
        server = grpc.server(futures.ThreadPoolExecutor(max_workers))

        yield server


# ArtifactShare()
#
# Abstract class providing scaffolding for
# generating data to be used with various sources
#
# Args:
#    directory (str): The base temp directory for the test
#    cache_quota (int): Maximum amount of disk space to use
#    casd (bool): Allow write access via casd
#    enable_push (bool): Whether the share should allow pushes
#
class ArtifactShare(BaseArtifactShare):
    def __init__(self, directory, *, quota=None, casd=False, index_only=False):

        # The working directory for the artifact share (in case it
        # needs to do something outside of its backend's storage folder).
        #
        self.directory = os.path.abspath(directory)

        # The directory the actual repo will be stored in.
        #
        # Unless this gets more complicated, just use this directly
        # in tests as a remote artifact push/pull configuration
        #
        self.repodir = os.path.join(self.directory, "repo")
        os.makedirs(self.repodir)
        self.artifactdir = os.path.join(self.repodir, "artifacts", "refs")
        os.makedirs(self.artifactdir)
        self.sourcedir = os.path.join(self.repodir, "source_protos", "refs")
        os.makedirs(self.sourcedir)

        logdir = os.path.join(self.directory, "logs") if casd else None

        self.cas = CASCache(self.repodir, casd=casd, log_directory=logdir)

        self.quota = quota
        self.index_only = index_only

        super().__init__()

    def _create_server(self):
        return create_server(self.repodir, quota=self.quota, enable_push=True, index_only=self.index_only,)

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

    def get_artifact_proto(self, artifact_name):
        artifact_proto = artifact_pb2.Artifact()
        artifact_path = os.path.join(self.artifactdir, artifact_name)

        try:
            with open(artifact_path, "rb") as f:
                artifact_proto.ParseFromString(f.read())
        except FileNotFoundError:
            return None

        return artifact_proto

    def get_source_proto(self, source_name):
        source_proto = source_pb2.Source()
        source_path = os.path.join(self.sourcedir, source_name)

        try:
            with open(source_path, "rb") as f:
                source_proto.ParseFromString(f.read())
        except FileNotFoundError:
            return None

        return source_proto

    def get_cas_files(self, artifact_proto):

        reachable = set()

        def reachable_dir(digest):
            self.cas._reachable_refs_dir(reachable, digest, update_mtime=False, check_exists=True)

        try:
            if str(artifact_proto.files):
                reachable_dir(artifact_proto.files)

            if str(artifact_proto.buildtree):
                reachable_dir(artifact_proto.buildtree)

            if str(artifact_proto.public_data):
                if not os.path.exists(self.cas.objpath(artifact_proto.public_data)):
                    return None

            for log_file in artifact_proto.logs:
                if not os.path.exists(self.cas.objpath(log_file.digest)):
                    return None

            return artifact_proto.files

        except CASError:
            return None

        except FileNotFoundError:
            return None

    # has_artifact():
    #
    # Checks whether the artifact is present in the share
    #
    # Args:
    #    artifact_name (str): The composed complete artifact name
    #
    # Returns:
    #    (ArtifactProto): artifact digest if the artifact exists in the share, otherwise None.
    def get_artifact(self, artifact_name):
        artifact_proto = self.get_artifact_proto(artifact_name)
        if not artifact_proto:
            return None
        return self.get_cas_files(artifact_proto)

    # close():
    #
    # Remove the artifact share.
    #
    def close(self):
        super().close()

        self.cas.release_resources()

        shutil.rmtree(self.directory)


# create_artifact_share()
#
# Create an ArtifactShare for use in a test case
#
@contextmanager
def create_artifact_share(directory, *, quota=None, casd=False):
    share = ArtifactShare(directory, quota=quota, casd=casd)
    try:
        yield share
    finally:
        share.close()


@contextmanager
def create_split_share(directory1, directory2, *, quota=None, casd=False):
    index = ArtifactShare(directory1, quota=quota, casd=casd, index_only=True)
    storage = ArtifactShare(directory2, quota=quota, casd=casd)

    try:
        yield index, storage
    finally:
        index.close()
        storage.close()


# create_dummy_artifact_share()
#
# Create a dummy artifact share that doesn't have any capabilities
#
@contextmanager
def create_dummy_artifact_share():
    share = DummyArtifactShare()
    try:
        yield share
    finally:
        share.close()


statvfs_result = namedtuple("statvfs_result", "f_blocks f_bfree f_bsize f_bavail")


# Assert that a given artifact is in the share
#
def assert_shared(cli, share, project, element_name, *, project_name="test"):
    if not share.get_artifact(cli.get_artifact_name(project, project_name, element_name)):
        raise AssertionError(
            "Artifact share at {} does not contain the expected element {}".format(share.repo, element_name)
        )


# Assert that a given artifact is not in the share
#
def assert_not_shared(cli, share, project, element_name, *, project_name="test"):
    if share.get_artifact(cli.get_artifact_name(project, project_name, element_name)):
        raise AssertionError(
            "Artifact share at {} unexpectedly contains the element {}".format(share.repo, element_name)
        )
