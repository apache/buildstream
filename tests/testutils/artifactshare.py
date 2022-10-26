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
import os
import shutil
import signal
from collections import namedtuple
from contextlib import ExitStack, contextmanager
from concurrent import futures
from multiprocessing import Process, Queue
from urllib.parse import urlparse

import grpc

from buildstream._cas import CASCache
from buildstream._cas.casserver import create_server
from buildstream._exceptions import CASError
from buildstream._protos.build.bazel.remote.asset.v1 import remote_asset_pb2, remote_asset_pb2_grpc
from buildstream._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from buildstream._protos.buildstream.v2 import artifact_pb2
from buildstream._protos.google.rpc import code_pb2

REMOTE_ASSET_ARTIFACT_URN_TEMPLATE = "urn:fdc:buildstream.build:2020:artifact:{}"
REMOTE_ASSET_SOURCE_URN_TEMPLATE = "urn:fdc:buildstream.build:2020:source:{}"


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
        # Block SIGTERM and SIGINT to allow graceful shutdown and cleanup after initialization
        signal.pthread_sigmask(signal.SIG_BLOCK, [signal.SIGTERM, signal.SIGINT])

        with ExitStack() as stack:
            try:
                server = stack.enter_context(self._create_server())
                port = server.add_insecure_port("127.0.0.1:0")
                server.start()
            except Exception:
                q.put(None)
                raise

            # Send port to parent
            q.put(port)

            # Sleep until termination by signal
            signal.sigwait([signal.SIGTERM, signal.SIGINT])

            server.stop(0)

        # Save collected coverage data
        try:
            from pytest_cov.embed import cleanup
        except ImportError:
            pass
        else:
            cleanup()

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
        assert self.process.exitcode == 0


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
#    enable_push (bool): Whether the share should allow pushes
#
class ArtifactShare(BaseArtifactShare):
    def __init__(self, directory, *, quota=None, index_only=False):

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

        self.cas = CASCache(self.repodir, casd=False)

        self.quota = quota
        self.index_only = index_only

        super().__init__()

    def _create_server(self):
        return create_server(
            self.repodir,
            quota=self.quota,
            enable_push=True,
            index_only=self.index_only,
        )

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
        url = urlparse(self.repo)
        channel = grpc.insecure_channel("{}:{}".format(url.hostname, url.port))
        try:
            fetch_service = remote_asset_pb2_grpc.FetchStub(channel)

            uri = REMOTE_ASSET_ARTIFACT_URN_TEMPLATE.format(artifact_name)

            request = remote_asset_pb2.FetchBlobRequest()
            request.uris.append(uri)

            try:
                response = fetch_service.FetchBlob(request)
            except grpc.RpcError as e:
                if e.code() == grpc.StatusCode.NOT_FOUND:
                    return None
                raise

            if response.status.code != code_pb2.OK:
                return None

            return response.blob_digest
        finally:
            channel.close()

    def get_source_proto(self, source_name):
        url = urlparse(self.repo)
        channel = grpc.insecure_channel("{}:{}".format(url.hostname, url.port))
        try:
            fetch_service = remote_asset_pb2_grpc.FetchStub(channel)

            uri = REMOTE_ASSET_SOURCE_URN_TEMPLATE.format(source_name)

            request = remote_asset_pb2.FetchDirectoryRequest()
            request.uris.append(uri)

            try:
                response = fetch_service.FetchDirectory(request)
            except grpc.RpcError as e:
                if e.code() == grpc.StatusCode.NOT_FOUND:
                    return None
                raise

            if response.status.code != code_pb2.OK:
                return None

            return response.root_directory_digest
        finally:
            channel.close()

    def get_cas_files(self, artifact_proto_digest):

        reachable = set()

        def reachable_dir(digest):
            self._reachable_refs_dir(reachable, digest)

        try:
            artifact_proto_path = self.cas.objpath(artifact_proto_digest)
            if not os.path.exists(artifact_proto_path):
                return None

            artifact_proto = artifact_pb2.Artifact()
            try:
                with open(artifact_proto_path, "rb") as f:
                    artifact_proto.ParseFromString(f.read())
            except FileNotFoundError:
                return None

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

        shutil.rmtree(self.directory)

    def _reachable_refs_dir(self, reachable, tree):
        if tree.hash in reachable:
            return

        reachable.add(tree.hash)

        directory = remote_execution_pb2.Directory()

        with open(self.cas.objpath(tree), "rb") as f:
            directory.ParseFromString(f.read())

        for filenode in directory.files:
            if not os.path.exists(self.cas.objpath(filenode.digest)):
                raise FileNotFoundError
            reachable.add(filenode.digest.hash)

        for dirnode in directory.directories:
            self._reachable_refs_dir(reachable, dirnode.digest)


# create_artifact_share()
#
# Create an ArtifactShare for use in a test case
#
@contextmanager
def create_artifact_share(directory, *, quota=None):
    share = ArtifactShare(directory, quota=quota)
    try:
        yield share
    finally:
        share.close()


@contextmanager
def create_split_share(directory1, directory2, *, quota=None):
    index = ArtifactShare(directory1, quota=quota, index_only=True)
    storage = ArtifactShare(directory2, quota=quota)

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
