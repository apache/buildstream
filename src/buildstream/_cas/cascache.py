#
#  Copyright (C) 2018 Codethink Limited
#  Copyright (C) 2018-2019 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#        Jürg Billeter <juerg.billeter@codethink.co.uk>

import itertools
import os
import stat
import contextlib
import ctypes
import multiprocessing
import signal
import time
from typing import Optional, List

import grpc

from .._protos.google.rpc import code_pb2
from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from .._protos.build.buildgrid import local_cas_pb2

from .. import _signals, utils
from ..types import FastEnum, SourceRef
from .._exceptions import CASCacheError

from .casdprocessmanager import CASDProcessManager
from .casremote import _CASBatchRead, _CASBatchUpdate

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
        protect_session_blobs=True,
        log_level=CASLogLevel.WARNING,
        log_directory=None
    ):
        self.casdir = os.path.join(path, "cas")
        self.tmpdir = os.path.join(path, "tmp")
        os.makedirs(self.tmpdir, exist_ok=True)

        self._cache_usage_monitor = None
        self._cache_usage_monitor_forbidden = False

        self._casd_process_manager = None
        self._casd_channel = None
        if casd:
            assert log_directory is not None, "log_directory is required when casd is True"
            log_dir = os.path.join(log_directory, "_casd")
            self._casd_process_manager = CASDProcessManager(
                path, log_dir, log_level, cache_quota, protect_session_blobs
            )

            self._casd_channel = self._casd_process_manager.create_channel()
            self._cache_usage_monitor = _CASCacheUsageMonitor(self._casd_channel)

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
        if self._cache_usage_monitor:
            self._cache_usage_monitor.release_resources()

        if self._casd_process_manager:
            self.close_grpc_channels()
            self._casd_process_manager.release_resources(messenger)
            self._casd_process_manager = None

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
        cas = self.get_cas()

        request = remote_execution_pb2.FindMissingBlobsRequest()
        request.blob_digests.extend(digests)

        response = cas.FindMissingBlobs(request)
        return len(response.missing_blob_digests) == 0

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

        request = local_cas_pb2.FetchTreeRequest()
        request.root_digest.CopyFrom(digest)
        request.fetch_file_blobs = with_files

        try:
            local_cas.FetchTree(request)
            return True
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return False
            if e.code() == grpc.StatusCode.UNIMPLEMENTED:
                raise CASCacheError("Unsupported buildbox-casd version: FetchTree unimplemented") from e
            raise

    # checkout():
    #
    # Checkout the specified directory digest.
    #
    # Args:
    #     dest (str): The destination path
    #     tree (Digest): The directory digest to extract
    #     can_link (bool): Whether we can create hard links in the destination
    #
    def checkout(self, dest, tree, *, can_link=False):
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
            self.checkout(fullpath, dirnode.digest, can_link=can_link)

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

    # add_object():
    #
    # Hash and write object to CAS.
    #
    # Args:
    #     digest (Digest): An optional Digest object to populate
    #     path (str): Path to file to add
    #     buffer (bytes): Byte buffer to add
    #     link_directly (bool): Whether file given by path can be linked
    #     instance_name (str): casd instance_name for remote CAS
    #
    # Returns:
    #     (Digest): The digest of the added object
    #
    # Either `path` or `buffer` must be passed, but not both.
    #
    def add_object(self, *, digest=None, path=None, buffer=None, link_directly=False, instance_name=None):
        # Exactly one of the two parameters has to be specified
        assert (path is None) != (buffer is None)

        # If we're linking directly, then path must be specified.
        assert (not link_directly) or (link_directly and path)

        if digest is None:
            digest = remote_execution_pb2.Digest()

        with contextlib.ExitStack() as stack:
            if path is None:
                tmp = stack.enter_context(self._temporary_object())
                tmp.write(buffer)
                tmp.flush()
                path = tmp.name

            request = local_cas_pb2.CaptureFilesRequest()
            if instance_name:
                request.instance_name = instance_name

            request.path.append(path)

            local_cas = self.get_local_cas()

            response = local_cas.CaptureFiles(request)

            if len(response.responses) != 1:
                raise CASCacheError("Expected 1 response from CaptureFiles, got {}".format(len(response.responses)))

            blob_response = response.responses[0]
            if blob_response.status.code == code_pb2.RESOURCE_EXHAUSTED:
                raise CASCacheError("Cache too full", reason="cache-too-full")
            if blob_response.status.code != code_pb2.OK:
                raise CASCacheError("Failed to capture blob {}: {}".format(path, blob_response.status.code))
            digest.CopyFrom(blob_response.digest)

        return digest

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
            raise CASCacheError("Failed to capture tree {}: {}".format(path, tree_response.status.code))

        treepath = self.objpath(tree_response.tree_digest)
        tree = remote_execution_pb2.Tree()
        with open(treepath, "rb") as f:
            tree.ParseFromString(f.read())

        root_directory = tree.root.SerializeToString()

        return utils._message_digest(root_directory)

    # remote_missing_blobs_for_directory():
    #
    # Determine which blobs of a directory tree are missing on the remote.
    #
    # Args:
    #     digest (Digest): The directory digest
    #
    # Returns: List of missing Digest objects
    #
    def remote_missing_blobs_for_directory(self, remote, digest):
        required_blobs = self.required_blobs_for_directory(digest)

        return self.remote_missing_blobs(remote, required_blobs)

    # remote_missing_blobs():
    #
    # Determine which blobs are missing on the remote.
    #
    # Args:
    #     blobs ([Digest]): List of directory digests to check
    #
    # Returns: List of missing Digest objects
    #
    def remote_missing_blobs(self, remote, blobs):
        cas = self.get_cas()
        instance_name = remote.local_cas_instance_name

        missing_blobs = dict()
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

    # local_missing_blobs():
    #
    # Check local cache for missing blobs.
    #
    # Args:
    #    digests (list): The Digests of blobs to check
    #
    # Returns: Missing Digest objects
    #
    def local_missing_blobs(self, digests):
        missing_blobs = []
        for digest in digests:
            objpath = self.objpath(digest)
            if not os.path.exists(objpath):
                missing_blobs.append(digest)
        return missing_blobs

    # required_blobs_for_directory():
    #
    # Generator that returns the Digests of all blobs in the tree specified by
    # the Digest of the toplevel Directory object.
    #
    def required_blobs_for_directory(self, directory_digest, *, excluded_subdirs=None):
        if not excluded_subdirs:
            excluded_subdirs = []

        # parse directory, and recursively add blobs

        yield directory_digest

        directory = remote_execution_pb2.Directory()

        with open(self.objpath(directory_digest), "rb") as f:
            directory.ParseFromString(f.read())

        for filenode in directory.files:
            yield filenode.digest

        for dirnode in directory.directories:
            if dirnode.name not in excluded_subdirs:
                yield from self.required_blobs_for_directory(dirnode.digest)

    ################################################
    #             Local Private Methods            #
    ################################################

    def _reachable_refs_dir(self, reachable, tree, update_mtime=False, check_exists=False):
        if tree.hash in reachable:
            return
        try:
            if update_mtime:
                os.utime(self.objpath(tree))

            reachable.add(tree.hash)

            directory = remote_execution_pb2.Directory()

            with open(self.objpath(tree), "rb") as f:
                directory.ParseFromString(f.read())

        except FileNotFoundError:
            if check_exists:
                raise

            # Just exit early if the file doesn't exist
            return

        for filenode in directory.files:
            if update_mtime:
                os.utime(self.objpath(filenode.digest))
            if check_exists:
                if not os.path.exists(self.objpath(filenode.digest)):
                    raise FileNotFoundError
            reachable.add(filenode.digest.hash)

        for dirnode in directory.directories:
            self._reachable_refs_dir(reachable, dirnode.digest, update_mtime=update_mtime, check_exists=check_exists)

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

    # _ensure_blob():
    #
    # Fetch and add blob if it's not already local.
    #
    # Args:
    #     remote (Remote): The remote to use.
    #     digest (Digest): Digest object for the blob to fetch.
    #
    # Returns:
    #     (str): The path of the object
    #
    def _ensure_blob(self, remote, digest):
        objpath = self.objpath(digest)
        if os.path.exists(objpath):
            # already in local repository
            return objpath

        batch = _CASBatchRead(remote)
        batch.add(digest)
        batch.send()

        return objpath

    # Helper function for _fetch_directory().
    def _fetch_directory_batch(self, remote, batch, fetch_queue, fetch_next_queue):
        batch.send()

        # All previously scheduled directories are now locally available,
        # move them to the processing queue.
        fetch_queue.extend(fetch_next_queue)
        fetch_next_queue.clear()
        return _CASBatchRead(remote)

    # Helper function for _fetch_directory().
    def _fetch_directory_node(self, remote, digest, batch, fetch_queue, fetch_next_queue, *, recursive=False):
        in_local_cache = os.path.exists(self.objpath(digest))

        if in_local_cache:
            # Skip download, already in local cache.
            pass
        else:
            batch.add(digest)

        if recursive:
            if in_local_cache:
                # Add directory to processing queue.
                fetch_queue.append(digest)
            else:
                # Directory will be available after completing pending batch.
                # Add directory to deferred processing queue.
                fetch_next_queue.append(digest)

        return batch

    # _fetch_directory():
    #
    # Fetches remote directory and adds it to content addressable store.
    #
    # This recursively fetches directory objects but doesn't fetch any
    # files.
    #
    # Args:
    #     remote (Remote): The remote to use.
    #     dir_digest (Digest): Digest object for the directory to fetch.
    #
    def _fetch_directory(self, remote, dir_digest):
        # TODO Use GetTree() if the server supports it

        fetch_queue = [dir_digest]
        fetch_next_queue = []
        batch = _CASBatchRead(remote)

        while len(fetch_queue) + len(fetch_next_queue) > 0:
            if not fetch_queue:
                batch = self._fetch_directory_batch(remote, batch, fetch_queue, fetch_next_queue)

            dir_digest = fetch_queue.pop(0)

            objpath = self._ensure_blob(remote, dir_digest)

            directory = remote_execution_pb2.Directory()
            with open(objpath, "rb") as f:
                directory.ParseFromString(f.read())

            for dirnode in directory.directories:
                batch = self._fetch_directory_node(
                    remote, dirnode.digest, batch, fetch_queue, fetch_next_queue, recursive=True
                )

        # Fetch final batch
        self._fetch_directory_batch(remote, batch, fetch_queue, fetch_next_queue)

    def _fetch_tree(self, remote, digest):
        objpath = self._ensure_blob(remote, digest)

        tree = remote_execution_pb2.Tree()

        with open(objpath, "rb") as f:
            tree.ParseFromString(f.read())

        tree.children.extend([tree.root])
        for directory in tree.children:
            dirbuffer = directory.SerializeToString()
            dirdigest = self.add_object(buffer=dirbuffer)
            assert dirdigest.size_bytes == len(dirbuffer)

        return dirdigest

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
        missing_blobs = [] if allow_partial else None

        remote.init()

        batch = _CASBatchRead(remote)

        for digest in digests:
            if digest.hash:
                batch.add(digest)

        batch.send(missing_blobs=missing_blobs)

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
class _CASCacheUsageMonitor:
    def __init__(self, connection):
        self._connection = connection

        # Shared memory (64-bit signed integer) for current disk usage and quota
        self._disk_usage = multiprocessing.Value(ctypes.c_longlong, -1)
        self._disk_quota = multiprocessing.Value(ctypes.c_longlong, -1)

        # multiprocessing.Process will fork without exec on Unix.
        # This can't be allowed with background threads or open gRPC channels.
        assert utils._is_single_threaded() and connection.is_closed()

        # Block SIGINT, we don't want to kill the process when we interrupt the frontend
        # and this process if very lightweight.
        with _signals.blocked([signal.SIGINT], ignore=False):
            self._subprocess = multiprocessing.Process(target=self._subprocess_run)
            self._subprocess.start()

    def get_cache_usage(self):
        disk_usage = self._disk_usage.value
        disk_quota = self._disk_quota.value

        if disk_usage < 0:
            # Disk usage still unknown
            disk_usage = None

        if disk_quota <= 0:
            # No disk quota
            disk_quota = None

        return _CASCacheUsage(disk_usage, disk_quota)

    def release_resources(self):
        # Simply terminate the subprocess, no cleanup required in the subprocess
        self._subprocess.terminate()

    def _subprocess_run(self):
        # Reset SIGTERM in subprocess to default as no cleanup is necessary
        signal.signal(signal.SIGTERM, signal.SIG_DFL)

        disk_usage = self._disk_usage
        disk_quota = self._disk_quota
        local_cas = self._connection.get_local_cas()

        while True:
            try:
                # Ask buildbox-casd for current value
                request = local_cas_pb2.GetLocalDiskUsageRequest()
                response = local_cas.GetLocalDiskUsage(request)

                # Update values in shared memory
                disk_usage.value = response.size_bytes
                disk_quota.value = response.quota_bytes
            except grpc.RpcError:
                # Terminate loop when buildbox-casd becomes unavailable
                break

            # Sleep until next refresh
            time.sleep(_CACHE_USAGE_REFRESH)


def _grouper(iterable, n):
    while True:
        try:
            current = next(iterable)
        except StopIteration:
            return
        yield itertools.chain([current], itertools.islice(iterable, n - 1))
