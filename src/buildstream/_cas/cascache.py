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
#  Authors:
#        Jürg Billeter <juerg.billeter@codethink.co.uk>

import itertools
import os
import stat
import contextlib
import time
from typing import Optional, List
import threading

import grpc

from .._protos.google.rpc import code_pb2
from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from .._protos.build.buildgrid import local_cas_pb2

from .. import utils
from ..types import FastEnum, SourceRef
from .._exceptions import CASCacheError

from .casdprocessmanager import CASDProcessManager
from .casremote import CASRemote, _CASBatchRead, _CASBatchUpdate, BlobNotFound

_BUFFER_SIZE = 65536


# Refresh interval for disk usage of local cache in seconds
_CACHE_USAGE_REFRESH = 5


class CASLogLevel(FastEnum):
    WARNING = "warning"
    INFO = "info"
    TRACE = "trace"


# A CASCache manages a CAS repository as specified in the Remote Execution API.
#
# Args:
#     path (str): The root directory for the CAS repository
#     casd (bool): True to spawn buildbox-casd (default) or False (testing only)
#     cache_quota (int): User configured cache quota
#     protect_session_blobs (bool): Disable expiry for blobs used in the current session
#     log_level (LogLevel): Log level to give to buildbox-casd for logging
#     log_directory (str): the root of the directory in which to store logs
#
class CASCache:
    def __init__(
        self,
        path,
        *,
        casd=True,
        cache_quota=None,
        remote_cache_spec=None,
        protect_session_blobs=True,
        log_level=CASLogLevel.WARNING,
        log_directory=None,
        messenger=None
    ):
        self.casdir = os.path.join(path, "cas")
        self.tmpdir = os.path.join(path, "tmp")
        os.makedirs(self.tmpdir, exist_ok=True)

        self._cache_usage_monitor = None
        self._cache_usage_monitor_forbidden = False

        self._remote_cache = bool(remote_cache_spec)

        self._casd_process_manager = None
        self._casd_channel = None
        if casd:
            assert log_directory is not None, "log_directory is required when casd is True"
            log_dir = os.path.join(log_directory, "_casd")
            self._casd_process_manager = CASDProcessManager(
                path, log_dir, log_level, cache_quota, remote_cache_spec, protect_session_blobs, messenger
            )

            self._casd_channel = self._casd_process_manager.create_channel()
            self._cache_usage_monitor = _CASCacheUsageMonitor(self._casd_channel)
            self._cache_usage_monitor.start()
        else:
            assert not self._remote_cache

        self._default_remote = CASRemote(None, self)
        self._default_remote.init()

    # get_cas():
    #
    # Return ContentAddressableStorage stub for buildbox-casd channel.
    #
    def get_cas(self):
        assert self._casd_channel, "CASCache was created without a channel"
        return self._casd_channel.get_cas()

    # get_local_cas():
    #
    # Return LocalCAS stub for buildbox-casd channel.
    #
    def get_local_cas(self):
        assert self._casd_channel, "CASCache was created without a channel"
        return self._casd_channel.get_local_cas()

    # preflight():
    #
    # Preflight check.
    #
    def preflight(self):
        if not os.path.join(self.casdir, "objects"):
            raise CASCacheError("CAS repository check failed for '{}'".format(self.casdir))

    # close_grpc_channels():
    #
    # Close the casd channel if it exists
    #
    def close_grpc_channels(self):
        if self._casd_channel:
            self._casd_channel.close()

    # release_resources():
    #
    # Release resources used by CASCache.
    #
    def release_resources(self, messenger=None):
        if self._casd_channel:
            self._casd_channel.request_shutdown()

        if self._cache_usage_monitor:
            self._cache_usage_monitor.stop()
            self._cache_usage_monitor.join()

        if self._casd_process_manager:
            self.close_grpc_channels()
            self._casd_process_manager.release_resources(messenger)
            self._casd_process_manager = None

    def get_default_remote(self):
        return self._default_remote

    # contains_files():
    #
    # Check whether file digests exist in the local CAS cache
    #
    # Args:
    #     digest (Digest): The file digest to check
    #
    # Returns: True if the files are in the cache, False otherwise
    #
    def contains_files(self, digests):
        return len(self.missing_blobs(digests)) == 0

    # contains_directory():
    #
    # Check whether the specified directory and subdirectories are in the cache,
    # i.e non dangling.
    #
    # Args:
    #     digest (Digest): The directory digest to check
    #     with_files (bool): Whether to check files as well
    #
    # Returns: True if the directory is available in the local cache
    #
    def contains_directory(self, digest, *, with_files):
        local_cas = self.get_local_cas()

        # Without a remote cache, `FetchTree` simply checks the local cache.
        request = local_cas_pb2.FetchTreeRequest()
        request.root_digest.CopyFrom(digest)
        # Always fetch Directory protos as they are needed to enumerate subdirectories and files.
        # Don't implicitly fetch file blobs from the remote cache as we don't need them.
        request.fetch_file_blobs = with_files and not self._remote_cache

        try:
            local_cas.FetchTree(request)
            if not self._remote_cache:
                return True
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return False
            if e.code() == grpc.StatusCode.UNIMPLEMENTED:
                raise CASCacheError("Unsupported buildbox-casd version: FetchTree unimplemented") from e
            raise

        # Check whether everything is available in the remote cache.
        missing_blobs = self.missing_blobs_for_directory(digest, remote=self._default_remote)
        return not missing_blobs

    # checkout():
    #
    # Checkout the specified directory digest.
    #
    # Args:
    #     dest (str): The destination path
    #     tree (Digest): The directory digest to extract
    #     can_link (bool): Whether we can create hard links in the destination
    #
    def checkout(self, dest, tree, *, can_link=False, _fetch=True):
        if _fetch and self._remote_cache:
            # We need the files in the local cache
            local_cas = self.get_local_cas()

            request = local_cas_pb2.FetchTreeRequest()
            request.root_digest.CopyFrom(tree)
            request.fetch_file_blobs = True

            local_cas.FetchTree(request)

        os.makedirs(dest, exist_ok=True)

        directory = remote_execution_pb2.Directory()

        with open(self.objpath(tree), "rb") as f:
            directory.ParseFromString(f.read())

        for filenode in directory.files:
            # regular file, create hardlink
            fullpath = os.path.join(dest, filenode.name)

            node_properties = filenode.node_properties
            if node_properties.HasField("mtime"):
                mtime = utils._parse_protobuf_timestamp(node_properties.mtime)
            else:
                mtime = None

            if can_link and mtime is None:
                utils.safe_link(self.objpath(filenode.digest), fullpath)
            else:
                utils.safe_copy(self.objpath(filenode.digest), fullpath, copystat=False)
                if mtime is not None:
                    utils._set_file_mtime(fullpath, mtime)

            if filenode.is_executable:
                st = os.stat(fullpath)
                mode = st.st_mode
                if mode & stat.S_IRUSR:
                    mode |= stat.S_IXUSR
                if mode & stat.S_IRGRP:
                    mode |= stat.S_IXGRP
                if mode & stat.S_IROTH:
                    mode |= stat.S_IXOTH
                os.chmod(fullpath, mode)

        for dirnode in directory.directories:
            fullpath = os.path.join(dest, dirnode.name)
            self.checkout(fullpath, dirnode.digest, can_link=can_link, _fetch=False)

        for symlinknode in directory.symlinks:
            # symlink
            fullpath = os.path.join(dest, symlinknode.name)
            os.symlink(symlinknode.target, fullpath)

    # pull_tree():
    #
    # Pull a single Tree rather than a ref.
    # Does not update local refs.
    #
    # Args:
    #     remote (CASRemote): The remote to pull from
    #     digest (Digest): The digest of the tree
    #
    def pull_tree(self, remote, digest):
        try:
            remote.init()

            digest = self._fetch_tree(remote, digest)

            return digest

        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.NOT_FOUND:
                raise

        return None

    # objpath():
    #
    # Return the path of an object based on its digest.
    #
    # Args:
    #     digest (Digest): The digest of the object
    #
    # Returns:
    #     (str): The path of the object
    #
    def objpath(self, digest):
        return os.path.join(self.casdir, "objects", digest.hash[:2], digest.hash[2:])

    # open():
    #
    # Open file read-only by CAS digest and return a corresponding file object.
    #
    # Args:
    #     digest (Digest): The digest of the object
    #     mode (str): An optional string that specifies the mode in which the file is opened.
    #
    def open(self, digest, mode="r"):
        if mode not in ["r", "rb"]:
            raise ValueError("Unsupported mode: `{}`".format(mode))

        objpath = self.objpath(digest)

        if self._remote_cache and not os.path.exists(objpath):
            batch = _CASBatchRead(self._default_remote)
            batch.add(digest)
            batch.send()

        return open(objpath, mode=mode)  # pylint: disable=consider-using-with,unspecified-encoding

    # add_object():
    #
    # Hash and write object to CAS.
    #
    # Args:
    #     path (str): Path to file to add
    #     buffer (bytes): Byte buffer to add
    #     instance_name (str): casd instance_name for remote CAS
    #
    # Returns:
    #     (Digest): The digest of the added object
    #
    # Either `path` or `buffer` must be passed, but not both.
    #
    def add_object(self, *, path=None, buffer=None, instance_name=None):
        # Exactly one of the two parameters has to be specified
        assert (path is None) != (buffer is None)
        if path is None:
            digests = self.add_objects(buffers=[buffer], instance_name=instance_name)
        else:
            digests = self.add_objects(paths=[path], instance_name=instance_name)
        assert len(digests) == 1
        return digests[0]

    # add_objects():
    #
    # Hash and write objects to CAS.
    #
    # Args:
    #     paths (List[str]): Paths to files to add
    #     buffers (List[bytes]): Byte buffers to add
    #     instance_name (str): casd instance_name for remote CAS
    #
    # Returns:
    #     (List[Digest]): The digests of the added objects
    #
    # Either `paths` or `buffers` must be passed, but not both.
    #
    def add_objects(self, *, paths=None, buffers=None, instance_name=None):
        # Exactly one of the two parameters has to be specified
        assert (paths is None) != (buffers is None)

        digests = []

        with contextlib.ExitStack() as stack:
            if paths is None:
                paths = []
                for buffer in buffers:
                    tmp = stack.enter_context(self._temporary_object())
                    tmp.write(buffer)
                    tmp.flush()
                    paths.append(tmp.name)

            request = local_cas_pb2.CaptureFilesRequest()
            if instance_name:
                request.instance_name = instance_name

            for path in paths:
                request.path.append(path)

            local_cas = self.get_local_cas()

            response = local_cas.CaptureFiles(request)

            if len(response.responses) != len(paths):
                raise CASCacheError(
                    "Expected {} responses from CaptureFiles, got {}".format(len(paths), len(response.responses))
                )

            for path, blob_response in zip(paths, response.responses):
                if blob_response.status.code == code_pb2.RESOURCE_EXHAUSTED:
                    raise CASCacheError("Cache too full", reason="cache-too-full")
                if blob_response.status.code != code_pb2.OK:
                    raise CASCacheError("Failed to capture blob {}: {}".format(path, blob_response.status.code))

                digest = remote_execution_pb2.Digest()
                digest.CopyFrom(blob_response.digest)
                digests.append(digest)

        return digests

    # import_directory():
    #
    # Import directory tree into CAS.
    #
    # Args:
    #     path (str): Path to directory to import
    #     properties Optional[List[str]]: List of properties to request
    #
    # Returns:
    #     (Digest): The digest of the imported directory
    #
    def import_directory(self, path: str, properties: Optional[List[str]] = None) -> SourceRef:
        local_cas = self.get_local_cas()

        request = local_cas_pb2.CaptureTreeRequest()
        request.path.append(path)

        if properties:
            for _property in properties:
                request.node_properties.append(_property)

        response = local_cas.CaptureTree(request)

        if len(response.responses) != 1:
            raise CASCacheError("Expected 1 response from CaptureTree, got {}".format(len(response.responses)))

        tree_response = response.responses[0]
        if tree_response.status.code == code_pb2.RESOURCE_EXHAUSTED:
            raise CASCacheError("Cache too full", reason="cache-too-full")
        if tree_response.status.code != code_pb2.OK:
            raise CASCacheError("Failed to capture tree {}: {}".format(path, tree_response.status))

        treepath = self.objpath(tree_response.tree_digest)
        tree = remote_execution_pb2.Tree()
        with open(treepath, "rb") as f:
            tree.ParseFromString(f.read())

        root_directory = tree.root.SerializeToString()

        return utils._message_digest(root_directory)

    # stage_directory():
    #
    # A contextmanager to stage a CAS directory tree in the local filesystem.
    #
    # This makes the specified directory tree temporarily available for local
    # filesystem access. This may use FUSE, hardlinks, reflinks or file copies,
    # depending on the system. The implementation makes sure that BuildStream
    # and subprocesses cannot corrupt the cache by modifying staged files.
    #
    # Args:
    #     directory_digest (Digest): The digest of a directory
    #
    # Yields:
    #     (str): The local filesystem path
    #
    @contextlib.contextmanager
    def stage_directory(self, directory_digest):
        local_cas = self.get_local_cas()

        request = local_cas_pb2.StageTreeRequest()
        request.root_digest.CopyFrom(directory_digest)

        # Specify the credentials used to access the staged tree
        request.access_credentials.uid = os.geteuid()

        done_event = threading.Event()

        def request_iterator():
            yield request

            # Wait until staged tree is no longer needed
            done_event.wait()

            # A second (empty) request indicates that the staging location can be cleaned up
            yield local_cas_pb2.StageTreeRequest()

        response_stream = local_cas.StageTree(request_iterator())

        try:
            # Read primary response and yield staging location
            response = next(response_stream)
            yield response.path

            # Staged tree is no longer needed
            done_event.set()
            # Wait for cleanup to complete
            next(response_stream)
        except StopIteration as e:
            raise CASCacheError("Unexpected end of response stream for StageTree") from e

    # missing_blobs_for_directory():
    #
    # Determine which blobs of a directory tree are missing on the remote.
    #
    # Args:
    #     digest (Digest): The directory digest
    #
    # Returns: List of missing Digest objects
    #
    def missing_blobs_for_directory(self, digest, *, remote=None):
        required_blobs = self.required_blobs_for_directory(digest)

        return self.missing_blobs(required_blobs, remote=remote)

    # missing_blobs():
    #
    # Determine which blobs are missing locally or on the remote.
    #
    # Args:
    #     blobs ([Digest]): List of directory digests to check
    #
    # Returns: List of missing Digest objects
    #
    def missing_blobs(self, blobs, *, remote=None):
        cas = self.get_cas()

        if remote:
            instance_name = remote.local_cas_instance_name
        else:
            instance_name = ""

        missing_blobs = {}
        # Limit size of FindMissingBlobs request
        for required_blobs_group in _grouper(iter(blobs), 512):
            request = remote_execution_pb2.FindMissingBlobsRequest(instance_name=instance_name)

            for required_digest in required_blobs_group:
                d = request.blob_digests.add()
                d.CopyFrom(required_digest)

            try:
                response = cas.FindMissingBlobs(request)
            except grpc.RpcError as e:
                if e.code() == grpc.StatusCode.INVALID_ARGUMENT and e.details().startswith("Invalid instance name"):
                    raise CASCacheError("Unsupported buildbox-casd version: FindMissingBlobs failed") from e
                raise

            for missing_digest in response.missing_blob_digests:
                d = remote_execution_pb2.Digest()
                d.CopyFrom(missing_digest)
                missing_blobs[d.hash] = d

        return missing_blobs.values()

    # required_blobs_for_directory():
    #
    # Generator that returns the Digests of all blobs in the tree specified by
    # the Digest of the toplevel Directory object.
    #
    def required_blobs_for_directory(self, directory_digest, *, excluded_subdirs=None, _fetch_tree=True):
        if not excluded_subdirs:
            excluded_subdirs = []

        if self._remote_cache and _fetch_tree:
            # Ensure we have the directory protos in the local cache
            local_cas = self.get_local_cas()

            request = local_cas_pb2.FetchTreeRequest()
            request.root_digest.CopyFrom(directory_digest)
            request.fetch_file_blobs = False

            local_cas.FetchTree(request)

        # parse directory, and recursively add blobs

        yield directory_digest

        directory = remote_execution_pb2.Directory()

        with open(self.objpath(directory_digest), "rb") as f:
            directory.ParseFromString(f.read())

        for filenode in directory.files:
            yield filenode.digest

        for dirnode in directory.directories:
            if dirnode.name not in excluded_subdirs:
                yield from self.required_blobs_for_directory(dirnode.digest, _fetch_tree=False)

    ################################################
    #             Local Private Methods            #
    ################################################

    # _temporary_object():
    #
    # Returns:
    #     (file): A file object to a named temporary file.
    #
    # Create a named temporary file with 0o0644 access rights.
    @contextlib.contextmanager
    def _temporary_object(self):
        with utils._tempnamedfile(dir=self.tmpdir) as f:
            os.chmod(f.name, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
            yield f

    # _fetch_directory():
    #
    # Fetches remote directory and adds it to content addressable store.
    #
    # This recursively fetches directory objects and files.
    #
    # Args:
    #     remote (Remote): The remote to use.
    #     dir_digest (Digest): Digest object for the directory to fetch.
    #
    def _fetch_directory(self, remote, dir_digest):
        local_cas = self.get_local_cas()

        request = local_cas_pb2.FetchTreeRequest()
        request.instance_name = remote.local_cas_instance_name
        request.root_digest.CopyFrom(dir_digest)
        request.fetch_file_blobs = False

        try:
            local_cas.FetchTree(request)
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise BlobNotFound(
                    dir_digest.hash,
                    "Failed to fetch directory tree {}: {}: {}".format(dir_digest.hash, e.code().name, e.details()),
                ) from e
            raise CASCacheError(
                "Failed to fetch directory tree {}: {}: {}".format(dir_digest.hash, e.code().name, e.details())
            ) from e

        required_blobs = self.required_blobs_for_directory(dir_digest)
        self.fetch_blobs(remote, required_blobs)

    def _fetch_tree(self, remote, digest):
        self.fetch_blobs(remote, [digest])

        tree = remote_execution_pb2.Tree()

        with self.open(digest, "rb") as f:
            tree.ParseFromString(f.read())

        dirbuffers = [tree.root.SerializeToString()]
        for directory in tree.children:
            dirbuffers.append(directory.SerializeToString())

        dirdigests = self.add_objects(buffers=dirbuffers)

        # The digest of the root directory
        return dirdigests[0]

    # fetch_blobs():
    #
    # Fetch blobs from remote CAS. Optionally returns missing blobs that could
    # not be fetched.
    #
    # Args:
    #    remote (CASRemote): The remote repository to fetch from
    #    digests (list): The Digests of blobs to fetch
    #    allow_partial (bool): True to return missing blobs, False to raise a
    #                          BlobNotFound error if a blob is missing
    #
    # Returns: The Digests of the blobs that were not available on the remote CAS
    #
    def fetch_blobs(self, remote, digests, *, allow_partial=False):
        if self._remote_cache:
            # Determine blobs missing in the remote cache and only fetch those
            digests = self.missing_blobs(digests)

        missing_blobs = [] if allow_partial else None

        remote.init()

        batch = _CASBatchRead(remote)

        for digest in digests:
            if digest.hash:
                batch.add(digest)

        batch.send(missing_blobs=missing_blobs)

        if self._remote_cache:
            # Upload fetched blobs to the remote cache as we can't transfer
            # blobs directly from another remote to the remote cache
            batch = _CASBatchUpdate(self._default_remote)
            for digest in digests:
                if missing_blobs is None or digest not in missing_blobs:  # pylint: disable=unsupported-membership-test
                    batch.add(digest)
            batch.send()

        return missing_blobs

    # send_blobs():
    #
    # Upload blobs to remote CAS.
    #
    # Args:
    #    remote (CASRemote): The remote repository to upload to
    #    digests (list): The Digests of Blobs to upload
    #
    def send_blobs(self, remote, digests):
        if self._remote_cache:
            # First fetch missing blobs from the remote cache as we can't
            # transfer blobs directly from the remote cache to another remote.

            remote_missing_blobs = self.missing_blobs(digests, remote=remote)

            batch = _CASBatchRead(self._default_remote)
            for digest in remote_missing_blobs:
                batch.add(digest)
            batch.send()

        batch = _CASBatchUpdate(remote)

        for digest in digests:
            batch.add(digest)

        batch.send()

    def _send_directory(self, remote, digest):
        required_blobs = self.required_blobs_for_directory(digest)

        # Upload any blobs missing on the server.
        # buildbox-casd will call FindMissingBlobs before the actual upload
        # and skip blobs that already exist on the server.
        self.send_blobs(remote, required_blobs)

    # get_cache_usage():
    #
    # Fetches the current usage of the CAS local cache.
    #
    # Returns:
    #     (CASCacheUsage): The current status
    #
    def get_cache_usage(self):
        assert not self._cache_usage_monitor_forbidden
        return self._cache_usage_monitor.get_cache_usage()

    # get_casd_process_manager()
    #
    # Get the underlying buildbox-casd process
    #
    # Returns:
    #   (subprocess.Process): The casd process that is used for the current cascache
    #
    def get_casd_process_manager(self):
        assert self._casd_process_manager is not None, "Only call this with a running buildbox-casd process"
        return self._casd_process_manager


# _CASCacheUsage
#
# A simple object to report the current CAS cache usage details.
#
# Args:
#    used_size (int): Total size used by the local cache, in bytes.
#    quota_size (int): Disk quota for the local cache, in bytes.
#
class _CASCacheUsage:
    def __init__(self, used_size, quota_size):
        self.used_size = used_size
        self.quota_size = quota_size
        if self.quota_size is None:
            self.used_percent = 0
        else:
            self.used_percent = int(self.used_size * 100 / self.quota_size)

    # Formattable into a human readable string
    #
    def __str__(self):
        if self.used_size is None:
            return "unknown"
        elif self.quota_size is None:
            return utils._pretty_size(self.used_size, dec_places=1)
        else:
            return "{} / {} ({}%)".format(
                utils._pretty_size(self.used_size, dec_places=1),
                utils._pretty_size(self.quota_size, dec_places=1),
                self.used_percent,
            )


# _CASCacheUsageMonitor
#
# This manages the subprocess that tracks cache usage information via
# buildbox-casd.
#
class _CASCacheUsageMonitor(threading.Thread):
    def __init__(self, connection):
        super().__init__()
        self._connection = connection
        self._disk_usage = None
        self._disk_quota = None
        self._should_stop = False

    def get_cache_usage(self):
        return _CASCacheUsage(self._disk_usage, self._disk_quota)

    def stop(self):
        self._should_stop = True

    def run(self):
        local_cas = self._connection.get_local_cas()

        while not self._should_stop:
            try:
                # Ask buildbox-casd for current value
                request = local_cas_pb2.GetLocalDiskUsageRequest()
                response = local_cas.GetLocalDiskUsage(request)

                # Update values in shared memory
                self._disk_usage = response.size_bytes
                disk_quota = response.quota_bytes
                if disk_quota == 0:  # Quota == 0 means there is no quota
                    self._disk_quota = None
                else:
                    self._disk_quota = disk_quota
            except grpc.RpcError:
                # Terminate loop when buildbox-casd becomes unavailable
                break

            # Sleep until next refresh
            for _ in range(_CACHE_USAGE_REFRESH * 10):
                if self._should_stop:
                    break
                time.sleep(0.1)


def _grouper(iterable, n):
    while True:
        try:
            current = next(iterable)
        except StopIteration:
            return
        yield itertools.chain([current], itertools.islice(iterable, n - 1))
