import os
import shutil
import signal
from collections import namedtuple

from contextlib import contextmanager
from multiprocessing import Process, Queue

from buildstream._cas import CASCache
from buildstream._cas.casserver import create_server
from buildstream._exceptions import CASError
from buildstream._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from buildstream._protos.buildstream.v2 import artifact_pb2


# ArtifactShare()
#
# Abstract class providing scaffolding for
# generating data to be used with various sources
#
# Args:
#    directory (str): The base temp directory for the test
#    cache_quota (int): Maximum amount of disk space to use
#    casd (bool): Allow write access via casd
#
class ArtifactShare():

    def __init__(self, directory, *, quota=None, casd=False):

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
        self.artifactdir = os.path.join(self.repodir, 'artifacts', 'refs')
        os.makedirs(self.artifactdir)

        self.cas = CASCache(self.repodir, casd=casd)

        self.quota = quota

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

        try:
            import pytest_cov
        except ImportError:
            pass
        else:
            pytest_cov.embed.cleanup_on_sigterm()

        try:
            with create_server(self.repodir,
                               quota=self.quota,
                               enable_push=True) as server:
                port = server.add_insecure_port('localhost:0')

                server.start()

                # Send port to parent
                q.put(port)

                # Sleep until termination by signal
                signal.pause()

        except Exception:
            q.put(None)
            raise

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
    #    artifact_name (str): The composed complete artifact name
    #
    # Returns:
    #    (str): artifact digest if the artifact exists in the share, otherwise None.
    def has_artifact(self, artifact_name):

        artifact_proto = artifact_pb2.Artifact()
        artifact_path = os.path.join(self.artifactdir, artifact_name)

        try:
            with open(artifact_path, 'rb') as f:
                artifact_proto.ParseFromString(f.read())
        except FileNotFoundError:
            return None

        reachable = set()

        def reachable_dir(digest):
            self.cas._reachable_refs_dir(
                reachable, digest, update_mtime=False, check_exists=True)

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

    # close():
    #
    # Remove the artifact share.
    #
    def close(self):
        self.process.terminate()
        self.process.join()

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


statvfs_result = namedtuple('statvfs_result', 'f_blocks f_bfree f_bsize f_bavail')


# Assert that a given artifact is in the share
#
def assert_shared(cli, share, project, element_name, *, project_name='test'):
    if not share.has_artifact(cli.get_artifact_name(project, project_name, element_name)):
        raise AssertionError("Artifact share at {} does not contain the expected element {}"
                             .format(share.repo, element_name))


# Assert that a given artifact is not in the share
#
def assert_not_shared(cli, share, project, element_name, *, project_name='test'):
    if share.has_artifact(cli.get_artifact_name(project, project_name, element_name)):
        raise AssertionError("Artifact share at {} unexpectedly contains the element {}"
                             .format(share.repo, element_name))
