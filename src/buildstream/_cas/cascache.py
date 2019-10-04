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
import errno
import contextlib
import ctypes
import multiprocessing
import shutil
import signal
import subprocess
import tempfile
import time

import grpc

from .._protos.google.rpc import code_pb2
from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2, remote_execution_pb2_grpc
from .._protos.build.buildgrid import local_cas_pb2, local_cas_pb2_grpc

from .. import _signals, utils
from .._exceptions import CASCacheError
from .._message import Message, MessageType

from .casremote import _CASBatchRead, _CASBatchUpdate

_BUFFER_SIZE = 65536


# Refresh interval for disk usage of local cache in seconds
_CACHE_USAGE_REFRESH = 5

_CASD_MAX_LOGFILES = 10


# A CASCache manages a CAS repository as specified in the Remote Execution API.
#
# Args:
#     path (str): The root directory for the CAS repository
#     casd (bool): True to spawn buildbox-casd (default) or False (testing only)
#     cache_quota (int): User configured cache quota
#     protect_session_blobs (bool): Disable expiry for blobs used in the current session
#
class CASCache():

    def __init__(self, path, *, casd=True, cache_quota=None, protect_session_blobs=True):
        self.casdir = os.path.join(path, 'cas')
        self.tmpdir = os.path.join(path, 'tmp')
        os.makedirs(os.path.join(self.casdir, 'refs', 'heads'), exist_ok=True)
        os.makedirs(os.path.join(self.casdir, 'objects'), exist_ok=True)
        os.makedirs(self.tmpdir, exist_ok=True)

        if casd:
            # Place socket in global/user temporary directory to avoid hitting
            # the socket path length limit.
            self._casd_socket_tempdir = tempfile.mkdtemp(prefix='buildstream')
            self._casd_socket_path = os.path.join(self._casd_socket_tempdir, 'casd.sock')

            casd_args = [utils.get_host_tool('buildbox-casd')]
            casd_args.append('--bind=unix:' + self._casd_socket_path)

            if cache_quota is not None:
                casd_args.append('--quota-high={}'.format(int(cache_quota)))
                casd_args.append('--quota-low={}'.format(int(cache_quota / 2)))

                if protect_session_blobs:
                    casd_args.append('--protect-session-blobs')

            casd_args.append(path)

            self._casd_start_time = time.time()
            self.casd_logfile = self._rotate_and_get_next_logfile()

            with open(self.casd_logfile, "w") as logfile_fp:
                # Block SIGINT on buildbox-casd, we don't need to stop it
                # The frontend will take care of it if needed
                with _signals.blocked([signal.SIGINT], ignore=False):
                    self._casd_process = subprocess.Popen(
                        casd_args, cwd=path, stdout=logfile_fp, stderr=subprocess.STDOUT)
        else:
            self._casd_process = None

        self._casd_channel = None
        self._casd_cas = None
        self._local_cas = None
        self._cache_usage_monitor = None

    def __getstate__(self):
        state = self.__dict__.copy()

        # Popen objects are not pickle-able, however, child processes only
        # need the information whether a casd subprocess was started or not.
        assert '_casd_process' in state
        state['_casd_process'] = bool(self._casd_process)

        return state

    def _init_casd(self):
        assert self._casd_process, "CASCache was instantiated without buildbox-casd"

        if not self._casd_channel:
            self._casd_channel = grpc.insecure_channel('unix:' + self._casd_socket_path)
            self._casd_cas = remote_execution_pb2_grpc.ContentAddressableStorageStub(self._casd_channel)
            self._local_cas = local_cas_pb2_grpc.LocalContentAddressableStorageStub(self._casd_channel)

            # Call GetCapabilities() to establish connection to casd
            capabilities = remote_execution_pb2_grpc.CapabilitiesStub(self._casd_channel)
            while True:
                try:
                    capabilities.GetCapabilities(remote_execution_pb2.GetCapabilitiesRequest())
                    break
                except grpc.RpcError as e:
                    if e.code() == grpc.StatusCode.UNAVAILABLE:
                        # casd is not ready yet, try again after a 10ms delay,
                        # but don't wait for more than 15s
                        if time.time() < self._casd_start_time + 15:
                            time.sleep(1 / 100)
                            continue

                    raise

    # _get_cas():
    #
    # Return ContentAddressableStorage stub for buildbox-casd channel.
    #
    def _get_cas(self):
        if not self._casd_cas:
            self._init_casd()
        return self._casd_cas

    # _get_local_cas():
    #
    # Return LocalCAS stub for buildbox-casd channel.
    #
    def _get_local_cas(self):
        if not self._local_cas:
            self._init_casd()
        return self._local_cas

    # preflight():
    #
    # Preflight check.
    #
    def preflight(self):
        headdir = os.path.join(self.casdir, 'refs', 'heads')
        objdir = os.path.join(self.casdir, 'objects')
        if not (os.path.isdir(headdir) and os.path.isdir(objdir)):
            raise CASCacheError("CAS repository check failed for '{}'".format(self.casdir))

    # has_open_grpc_channels():
    #
    # Return whether there are gRPC channel instances. This is used to safeguard
    # against fork() with open gRPC channels.
    #
    def has_open_grpc_channels(self):
        return bool(self._casd_channel)

    # close_channel():
    #
    # Close the casd channel if it exists
    #
    def close_channel(self):
        if self._casd_channel:
            self._local_cas = None
            self._casd_channel.close()
            self._casd_channel = None

    # release_resources():
    #
    # Release resources used by CASCache.
    #
    def release_resources(self, messenger=None):
        if self._cache_usage_monitor:
            self._cache_usage_monitor.release_resources()

        if self._casd_process:
            self.close_channel()
            self._terminate_casd_process(messenger)
            shutil.rmtree(self._casd_socket_tempdir)

    # contains():
    #
    # Check whether the specified ref is already available in the local CAS cache.
    #
    # Args:
    #     ref (str): The ref to check
    #
    # Returns: True if the ref is in the cache, False otherwise
    #
    def contains(self, ref):
        refpath = self._refpath(ref)

        # This assumes that the repository doesn't have any dangling pointers
        return os.path.exists(refpath)

    # contains_file():
    #
    # Check whether a digest corresponds to a file which exists in CAS
    #
    # Args:
    #     digest (Digest): The file digest to check
    #
    # Returns: True if the file is in the cache, False otherwise
    #
    def contains_file(self, digest):
        return os.path.exists(self.objpath(digest))

    # contains_directory():
    #
    # Check whether the specified directory and subdirectories are in the cache,
    # i.e non dangling.
    #
    # Args:
    #     digest (Digest): The directory digest to check
    #     with_files (bool): Whether to check files as well
    #     update_mtime (bool): Whether to update the timestamp
    #
    # Returns: True if the directory is available in the local cache
    #
    def contains_directory(self, digest, *, with_files, update_mtime=False):
        try:
            directory = remote_execution_pb2.Directory()
            path = self.objpath(digest)
            with open(path, 'rb') as f:
                directory.ParseFromString(f.read())
                if update_mtime:
                    os.utime(f.fileno())

            # Optionally check presence of files
            if with_files:
                for filenode in directory.files:
                    path = self.objpath(filenode.digest)
                    if update_mtime:
                        # No need for separate `exists()` call as this will raise
                        # FileNotFoundError if the file does not exist.
                        os.utime(path)
                    elif not os.path.exists(path):
                        return False

            # Check subdirectories
            for dirnode in directory.directories:
                if not self.contains_directory(dirnode.digest, with_files=with_files, update_mtime=update_mtime):
                    return False

            return True
        except FileNotFoundError:
            return False

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

        with open(self.objpath(tree), 'rb') as f:
            directory.ParseFromString(f.read())

        for filenode in directory.files:
            # regular file, create hardlink
            fullpath = os.path.join(dest, filenode.name)
            if can_link:
                utils.safe_link(self.objpath(filenode.digest), fullpath)
            else:
                utils.safe_copy(self.objpath(filenode.digest), fullpath)

            if filenode.is_executable:
                os.chmod(fullpath, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR |
                         stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

        for dirnode in directory.directories:
            fullpath = os.path.join(dest, dirnode.name)
            self.checkout(fullpath, dirnode.digest, can_link=can_link)

        for symlinknode in directory.symlinks:
            # symlink
            fullpath = os.path.join(dest, symlinknode.name)
            os.symlink(symlinknode.target, fullpath)

    # diff():
    #
    # Return a list of files that have been added or modified between
    # the refs described by ref_a and ref_b.
    #
    # Args:
    #     ref_a (str): The first ref
    #     ref_b (str): The second ref
    #     subdir (str): A subdirectory to limit the comparison to
    #
    def diff(self, ref_a, ref_b):
        tree_a = self.resolve_ref(ref_a)
        tree_b = self.resolve_ref(ref_b)

        added = []
        removed = []
        modified = []

        self.diff_trees(tree_a, tree_b, added=added, removed=removed, modified=modified)

        return modified, removed, added

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
        return os.path.join(self.casdir, 'objects', digest.hash[:2], digest.hash[2:])

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

            local_cas = self._get_local_cas()

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
    #
    # Returns:
    #     (Digest): The digest of the imported directory
    #
    def import_directory(self, path):
        local_cas = self._get_local_cas()

        request = local_cas_pb2.CaptureTreeRequest()
        request.path.append(path)
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
        with open(treepath, 'rb') as f:
            tree.ParseFromString(f.read())

        root_directory = tree.root.SerializeToString()

        return utils._message_digest(root_directory)

    # set_ref():
    #
    # Create or replace a ref.
    #
    # Args:
    #     ref (str): The name of the ref
    #
    def set_ref(self, ref, tree):
        refpath = self._refpath(ref)
        os.makedirs(os.path.dirname(refpath), exist_ok=True)
        with utils.save_file_atomic(refpath, 'wb', tempdir=self.tmpdir) as f:
            f.write(tree.SerializeToString())

    # resolve_ref():
    #
    # Resolve a ref to a digest.
    #
    # Args:
    #     ref (str): The name of the ref
    #     update_mtime (bool): Whether to update the mtime of the ref
    #
    # Returns:
    #     (Digest): The digest stored in the ref
    #
    def resolve_ref(self, ref, *, update_mtime=False):
        refpath = self._refpath(ref)

        try:
            with open(refpath, 'rb') as f:
                if update_mtime:
                    os.utime(refpath)

                digest = remote_execution_pb2.Digest()
                digest.ParseFromString(f.read())
                return digest

        except FileNotFoundError as e:
            raise CASCacheError("Attempt to access unavailable ref: {}".format(e)) from e

    # update_mtime()
    #
    # Update the mtime of a ref.
    #
    # Args:
    #     ref (str): The ref to update
    #
    def update_mtime(self, ref):
        try:
            os.utime(self._refpath(ref))
        except FileNotFoundError as e:
            raise CASCacheError("Attempt to access unavailable ref: {}".format(e)) from e

    # remove():
    #
    # Removes the given symbolic ref from the repo.
    #
    # Args:
    #    ref (str): A symbolic ref
    #    basedir (str): Path of base directory the ref is in, defaults to
    #                   CAS refs heads
    #
    def remove(self, ref, *, basedir=None):

        if basedir is None:
            basedir = os.path.join(self.casdir, 'refs', 'heads')
        # Remove cache ref
        self._remove_ref(ref, basedir)

    def update_tree_mtime(self, tree):
        reachable = set()
        self._reachable_refs_dir(reachable, tree, update_mtime=True)

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
        cas = self._get_cas()
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

        with open(self.objpath(directory_digest), 'rb') as f:
            directory.ParseFromString(f.read())

        for filenode in directory.files:
            yield filenode.digest

        for dirnode in directory.directories:
            if dirnode.name not in excluded_subdirs:
                yield from self.required_blobs_for_directory(dirnode.digest)

    def diff_trees(self, tree_a, tree_b, *, added, removed, modified, path=""):
        dir_a = remote_execution_pb2.Directory()
        dir_b = remote_execution_pb2.Directory()

        if tree_a:
            with open(self.objpath(tree_a), 'rb') as f:
                dir_a.ParseFromString(f.read())
        if tree_b:
            with open(self.objpath(tree_b), 'rb') as f:
                dir_b.ParseFromString(f.read())

        a = 0
        b = 0
        while a < len(dir_a.files) or b < len(dir_b.files):
            if b < len(dir_b.files) and (a >= len(dir_a.files) or
                                         dir_a.files[a].name > dir_b.files[b].name):
                added.append(os.path.join(path, dir_b.files[b].name))
                b += 1
            elif a < len(dir_a.files) and (b >= len(dir_b.files) or
                                           dir_b.files[b].name > dir_a.files[a].name):
                removed.append(os.path.join(path, dir_a.files[a].name))
                a += 1
            else:
                # File exists in both directories
                if dir_a.files[a].digest.hash != dir_b.files[b].digest.hash:
                    modified.append(os.path.join(path, dir_a.files[a].name))
                a += 1
                b += 1

        a = 0
        b = 0
        while a < len(dir_a.directories) or b < len(dir_b.directories):
            if b < len(dir_b.directories) and (a >= len(dir_a.directories) or
                                               dir_a.directories[a].name > dir_b.directories[b].name):
                self.diff_trees(None, dir_b.directories[b].digest,
                                added=added, removed=removed, modified=modified,
                                path=os.path.join(path, dir_b.directories[b].name))
                b += 1
            elif a < len(dir_a.directories) and (b >= len(dir_b.directories) or
                                                 dir_b.directories[b].name > dir_a.directories[a].name):
                self.diff_trees(dir_a.directories[a].digest, None,
                                added=added, removed=removed, modified=modified,
                                path=os.path.join(path, dir_a.directories[a].name))
                a += 1
            else:
                # Subdirectory exists in both directories
                if dir_a.directories[a].digest.hash != dir_b.directories[b].digest.hash:
                    self.diff_trees(dir_a.directories[a].digest, dir_b.directories[b].digest,
                                    added=added, removed=removed, modified=modified,
                                    path=os.path.join(path, dir_a.directories[a].name))
                a += 1
                b += 1

    ################################################
    #             Local Private Methods            #
    ################################################

    # _rotate_and_get_next_logfile()
    #
    # Get the logfile to use for casd
    #
    # This will ensure that we don't create too many casd log files by
    # rotating the logs and only keeping _CASD_MAX_LOGFILES logs around.
    #
    # Returns:
    #   (str): the path to the log file to use
    #
    def _rotate_and_get_next_logfile(self):
        log_dir = os.path.join(self.casdir, "logs")

        try:
            existing_logs = sorted(os.listdir(log_dir))
        except FileNotFoundError:
            os.makedirs(log_dir)
        else:
            while len(existing_logs) >= _CASD_MAX_LOGFILES:
                logfile_to_delete = existing_logs.pop(0)
                os.remove(os.path.join(log_dir, logfile_to_delete))

        return os.path.join(log_dir, str(self._casd_start_time) + ".log")

    def _refpath(self, ref):
        return os.path.join(self.casdir, 'refs', 'heads', ref)

    # _remove_ref()
    #
    # Removes a ref.
    #
    # This also takes care of pruning away directories which can
    # be removed after having removed the given ref.
    #
    # Args:
    #    ref (str): The ref to remove
    #    basedir (str): Path of base directory the ref is in
    #
    # Raises:
    #    (CASCacheError): If the ref didnt exist, or a system error
    #                     occurred while removing it
    #
    def _remove_ref(self, ref, basedir):

        # Remove the ref itself
        refpath = os.path.join(basedir, ref)

        try:
            os.unlink(refpath)
        except FileNotFoundError as e:
            raise CASCacheError("Could not find ref '{}'".format(ref)) from e

        # Now remove any leading directories

        components = list(os.path.split(ref))
        while components:
            components.pop()
            refdir = os.path.join(basedir, *components)

            # Break out once we reach the base
            if refdir == basedir:
                break

            try:
                os.rmdir(refdir)
            except FileNotFoundError:
                # The parent directory did not exist, but it's
                # parent directory might still be ready to prune
                pass
            except OSError as e:
                if e.errno == errno.ENOTEMPTY:
                    # The parent directory was not empty, so we
                    # cannot prune directories beyond this point
                    break

                # Something went wrong here
                raise CASCacheError("System error while removing ref '{}': {}".format(ref, e)) from e

    def _get_subdir(self, tree, subdir):
        head, name = os.path.split(subdir)
        if head:
            tree = self._get_subdir(tree, head)

        directory = remote_execution_pb2.Directory()

        with open(self.objpath(tree), 'rb') as f:
            directory.ParseFromString(f.read())

        for dirnode in directory.directories:
            if dirnode.name == name:
                return dirnode.digest

        raise CASCacheError("Subdirectory {} not found".format(name))

    def _reachable_refs_dir(self, reachable, tree, update_mtime=False, check_exists=False):
        if tree.hash in reachable:
            return
        try:
            if update_mtime:
                os.utime(self.objpath(tree))

            reachable.add(tree.hash)

            directory = remote_execution_pb2.Directory()

            with open(self.objpath(tree), 'rb') as f:
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
            os.chmod(f.name,
                     stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
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
            with open(objpath, 'rb') as f:
                directory.ParseFromString(f.read())

            for dirnode in directory.directories:
                batch = self._fetch_directory_node(remote, dirnode.digest, batch,
                                                   fetch_queue, fetch_next_queue, recursive=True)

        # Fetch final batch
        self._fetch_directory_batch(remote, batch, fetch_queue, fetch_next_queue)

    def _fetch_tree(self, remote, digest):
        objpath = self._ensure_blob(remote, digest)

        tree = remote_execution_pb2.Tree()

        with open(objpath, 'rb') as f:
            tree.ParseFromString(f.read())

        tree.children.extend([tree.root])
        for directory in tree.children:
            dirbuffer = directory.SerializeToString()
            dirdigest = self.add_object(buffer=dirbuffer)
            assert dirdigest.size_bytes == len(dirbuffer)

        return dirdigest

    # fetch_blobs():
    #
    # Fetch blobs from remote CAS. Returns missing blobs that could not be fetched.
    #
    # Args:
    #    remote (CASRemote): The remote repository to fetch from
    #    digests (list): The Digests of blobs to fetch
    #
    # Returns: The Digests of the blobs that were not available on the remote CAS
    #
    def fetch_blobs(self, remote, digests):
        missing_blobs = []

        remote.init()

        batch = _CASBatchRead(remote)

        for digest in digests:
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
        missing_blobs = self.remote_missing_blobs_for_directory(remote, digest)

        # Upload any blobs missing on the server
        self.send_blobs(remote, missing_blobs)

    # _terminate_casd_process()
    #
    # Terminate the buildbox casd process
    #
    # Args:
    #   messenger (buildstream._messenger.Messenger): Messenger to forward information to the frontend
    #
    def _terminate_casd_process(self, messenger=None):
        return_code = self._casd_process.poll()

        if return_code is not None:
            # buildbox-casd is already dead
            self._casd_process = None

            if messenger:
                messenger.message(
                    Message(
                        MessageType.BUG,
                        "Buildbox-casd died during the run. Exit code: {}, Logs: {}".format(
                            return_code, self.casd_logfile
                        ),
                    )
                )
            return

        self._casd_process.terminate()

        try:
            # Don't print anything if buildbox-casd terminates quickly
            return_code = self._casd_process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            if messenger:
                cm = messenger.timed_activity("Terminating buildbox-casd")
            else:
                cm = contextlib.suppress()
            with cm:
                try:
                    return_code = self._casd_process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    self._casd_process.kill()
                    self._casd_process.wait(timeout=15)

                    if messenger:
                        messenger.message(
                            Message(MessageType.WARN, "Buildbox-casd didn't exit in time and has been killed")
                        )
                    self._casd_process = None
                    return

        if return_code != 0 and messenger:
            messenger.message(
                Message(
                    MessageType.BUG,
                    "Buildbox-casd didn't exit cleanly. Exit code: {}, Logs: {}".format(
                        return_code, self.casd_logfile
                    ),
                )
            )

        self._casd_process = None

    # get_cache_usage():
    #
    # Fetches the current usage of the CAS local cache.
    #
    # Returns:
    #     (CASCacheUsage): The current status
    #
    def get_cache_usage(self):
        if not self._cache_usage_monitor:
            self._cache_usage_monitor = _CASCacheUsageMonitor(self)

        return self._cache_usage_monitor.get_cache_usage()


# _CASCacheUsage
#
# A simple object to report the current CAS cache usage details.
#
# Args:
#    used_size (int): Total size used by the local cache, in bytes.
#    quota_size (int): Disk quota for the local cache, in bytes.
#
class _CASCacheUsage():

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
            return "{} / {} ({}%)" \
                .format(utils._pretty_size(self.used_size, dec_places=1),
                        utils._pretty_size(self.quota_size, dec_places=1),
                        self.used_percent)


# _CASCacheUsageMonitor
#
# This manages the subprocess that tracks cache usage information via
# buildbox-casd.
#
class _CASCacheUsageMonitor:
    def __init__(self, cas):
        self.cas = cas

        # Shared memory (64-bit signed integer) for current disk usage and quota
        self._disk_usage = multiprocessing.Value(ctypes.c_longlong, -1)
        self._disk_quota = multiprocessing.Value(ctypes.c_longlong, -1)

        # multiprocessing.Process will fork without exec on Unix.
        # This can't be allowed with background threads or open gRPC channels.
        assert utils._is_single_threaded() and not cas.has_open_grpc_channels()

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
        local_cas = self.cas._get_local_cas()

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
