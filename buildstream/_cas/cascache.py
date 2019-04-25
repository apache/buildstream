#
#  Copyright (C) 2018 Codethink Limited
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

import hashlib
import itertools
import os
import stat
import uuid
import contextlib

import grpc

from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from .._protos.buildstream.v2 import buildstream_pb2

from .. import utils
from .._exceptions import CASCacheError, LoadError, LoadErrorReason
from .._message import Message, MessageType

from .casremote import BlobNotFound, _CASBatchRead, _CASBatchUpdate

_BUFFER_SIZE = 65536


CACHE_SIZE_FILE = "cache_size"


# CASCacheUsage
#
# A simple object to report the current CAS cache usage details.
#
# Note that this uses the user configured cache quota
# rather than the internal quota with protective headroom
# removed, to provide a more sensible value to display to
# the user.
#
# Args:
#    cas (CASQuota): The CAS cache to get the status of
#
class CASCacheUsage():

    def __init__(self, casquota):
        self.quota_config = casquota._config_cache_quota          # Configured quota
        self.quota_size = casquota._cache_quota_original          # Resolved cache quota in bytes
        self.used_size = casquota.get_cache_size()                # Size used by artifacts in bytes
        self.used_percent = 0                                # Percentage of the quota used
        if self.quota_size is not None:
            self.used_percent = int(self.used_size * 100 / self.quota_size)

    # Formattable into a human readable string
    #
    def __str__(self):
        return "{} / {} ({}%)" \
            .format(utils._pretty_size(self.used_size, dec_places=1),
                    self.quota_config,
                    self.used_percent)


# A CASCache manages a CAS repository as specified in the Remote Execution API.
#
# Args:
#     path (str): The root directory for the CAS repository
#     cache_quota (int): User configured cache quota
#
class CASCache():

    def __init__(self, path):
        self.casdir = os.path.join(path, 'cas')
        self.tmpdir = os.path.join(path, 'tmp')
        os.makedirs(os.path.join(self.casdir, 'refs', 'heads'), exist_ok=True)
        os.makedirs(os.path.join(self.casdir, 'objects'), exist_ok=True)
        os.makedirs(self.tmpdir, exist_ok=True)

        self.__reachable_directory_callbacks = []
        self.__reachable_digest_callbacks = []

    # preflight():
    #
    # Preflight check.
    #
    def preflight(self):
        headdir = os.path.join(self.casdir, 'refs', 'heads')
        objdir = os.path.join(self.casdir, 'objects')
        if not (os.path.isdir(headdir) and os.path.isdir(objdir)):
            raise CASCacheError("CAS repository check failed for '{}'".format(self.casdir))

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

    # contains_subdir_artifact():
    #
    # Check whether the specified artifact element tree has a digest for a subdir
    # which is populated in the cache, i.e non dangling.
    #
    # Args:
    #     ref (str): The ref to check
    #     subdir (str): The subdir to check
    #     with_files (bool): Whether to check files as well
    #
    # Returns: True if the subdir exists & is populated in the cache, False otherwise
    #
    def contains_subdir_artifact(self, ref, subdir, *, with_files=True):
        tree = self.resolve_ref(ref)

        try:
            subdirdigest = self._get_subdir(tree, subdir)

            return self.contains_directory(subdirdigest, with_files=with_files)
        except (CASCacheError, FileNotFoundError):
            return False

    # contains_directory():
    #
    # Check whether the specified directory and subdirecotires are in the cache,
    # i.e non dangling.
    #
    # Args:
    #     digest (Digest): The directory digest to check
    #     with_files (bool): Whether to check files as well
    #
    # Returns: True if the directory is available in the local cache
    #
    def contains_directory(self, digest, *, with_files):
        try:
            directory = remote_execution_pb2.Directory()
            with open(self.objpath(digest), 'rb') as f:
                directory.ParseFromString(f.read())

            # Optionally check presence of files
            if with_files:
                for filenode in directory.files:
                    if not os.path.exists(self.objpath(filenode.digest)):
                        return False

            # Check subdirectories
            for dirnode in directory.directories:
                if not self.contains_directory(dirnode.digest, with_files=with_files):
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

    # commit():
    #
    # Commit directory to cache.
    #
    # Args:
    #     refs (list): The refs to set
    #     path (str): The directory to import
    #
    def commit(self, refs, path):
        tree = self._commit_directory(path)

        for ref in refs:
            self.set_ref(ref, tree)

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

    # pull():
    #
    # Pull a ref from a remote repository.
    #
    # Args:
    #     ref (str): The ref to pull
    #     remote (CASRemote): The remote repository to pull from
    #
    # Returns:
    #   (bool): True if pull was successful, False if ref was not available
    #
    def pull(self, ref, remote):
        try:
            remote.init()

            request = buildstream_pb2.GetReferenceRequest(instance_name=remote.spec.instance_name)
            request.key = ref
            response = remote.ref_storage.GetReference(request)

            tree = response.digest

            # Fetch Directory objects
            self._fetch_directory(remote, tree)

            # Fetch files, excluded_subdirs determined in pullqueue
            required_blobs = self.required_blobs_for_directory(tree)
            missing_blobs = self.local_missing_blobs(required_blobs)
            if missing_blobs:
                self.fetch_blobs(remote, missing_blobs)

            self.set_ref(ref, tree)

            return True
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.NOT_FOUND:
                raise CASCacheError("Failed to pull ref {}: {}".format(ref, e)) from e
            else:
                return False
        except BlobNotFound as e:
            return False

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

    # link_ref():
    #
    # Add an alias for an existing ref.
    #
    # Args:
    #     oldref (str): An existing ref
    #     newref (str): A new ref for the same directory
    #
    def link_ref(self, oldref, newref):
        tree = self.resolve_ref(oldref)

        self.set_ref(newref, tree)

    # push():
    #
    # Push committed refs to remote repository.
    #
    # Args:
    #     refs (list): The refs to push
    #     remote (CASRemote): The remote to push to
    #
    # Returns:
    #   (bool): True if any remote was updated, False if no pushes were required
    #
    # Raises:
    #   (CASCacheError): if there was an error
    #
    def push(self, refs, remote):
        skipped_remote = True
        try:
            for ref in refs:
                tree = self.resolve_ref(ref)

                # Check whether ref is already on the server in which case
                # there is no need to push the ref
                try:
                    request = buildstream_pb2.GetReferenceRequest(instance_name=remote.spec.instance_name)
                    request.key = ref
                    response = remote.ref_storage.GetReference(request)

                    if response.digest.hash == tree.hash and response.digest.size_bytes == tree.size_bytes:
                        # ref is already on the server with the same tree
                        continue

                except grpc.RpcError as e:
                    if e.code() != grpc.StatusCode.NOT_FOUND:
                        # Intentionally re-raise RpcError for outer except block.
                        raise

                self._send_directory(remote, tree)

                request = buildstream_pb2.UpdateReferenceRequest(instance_name=remote.spec.instance_name)
                request.keys.append(ref)
                request.digest.CopyFrom(tree)
                remote.ref_storage.UpdateReference(request)

                skipped_remote = False
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.RESOURCE_EXHAUSTED:
                raise CASCacheError("Failed to push ref {}: {}".format(refs, e), temporary=True) from e

        return not skipped_remote

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
    #
    # Returns:
    #     (Digest): The digest of the added object
    #
    # Either `path` or `buffer` must be passed, but not both.
    #
    def add_object(self, *, digest=None, path=None, buffer=None, link_directly=False):
        # Exactly one of the two parameters has to be specified
        assert (path is None) != (buffer is None)

        if digest is None:
            digest = remote_execution_pb2.Digest()

        try:
            h = hashlib.sha256()
            # Always write out new file to avoid corruption if input file is modified
            with contextlib.ExitStack() as stack:
                if path is not None and link_directly:
                    tmp = stack.enter_context(open(path, 'rb'))
                    for chunk in iter(lambda: tmp.read(_BUFFER_SIZE), b""):
                        h.update(chunk)
                else:
                    tmp = stack.enter_context(self._temporary_object())

                    if path:
                        with open(path, 'rb') as f:
                            for chunk in iter(lambda: f.read(_BUFFER_SIZE), b""):
                                h.update(chunk)
                                tmp.write(chunk)
                    else:
                        h.update(buffer)
                        tmp.write(buffer)

                    tmp.flush()

                digest.hash = h.hexdigest()
                digest.size_bytes = os.fstat(tmp.fileno()).st_size

                # Place file at final location
                objpath = self.objpath(digest)
                os.makedirs(os.path.dirname(objpath), exist_ok=True)
                os.link(tmp.name, objpath)

        except FileExistsError as e:
            # We can ignore the failed link() if the object is already in the repo.
            pass

        except OSError as e:
            raise CASCacheError("Failed to hash object: {}".format(e)) from e

        return digest

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

    # list_objects():
    #
    # List cached objects in Least Recently Modified (LRM) order.
    #
    # Returns:
    #     (list) - A list of objects and timestamps in LRM order
    #
    def list_objects(self):
        objs = []
        mtimes = []

        for root, _, files in os.walk(os.path.join(self.casdir, 'objects')):
            for filename in files:
                obj_path = os.path.join(root, filename)
                try:
                    mtimes.append(os.path.getmtime(obj_path))
                except FileNotFoundError:
                    pass
                else:
                    objs.append(obj_path)

        # NOTE: Sorted will sort from earliest to latest, thus the
        # first element of this list will be the file modified earliest.
        return sorted(zip(mtimes, objs))

    def clean_up_refs_until(self, time):
        ref_heads = os.path.join(self.casdir, 'refs', 'heads')

        for root, _, files in os.walk(ref_heads):
            for filename in files:
                ref_path = os.path.join(root, filename)
                # Obtain the mtime (the time a file was last modified)
                if os.path.getmtime(ref_path) < time:
                    os.unlink(ref_path)

    # remove():
    #
    # Removes the given symbolic ref from the repo.
    #
    # Args:
    #    ref (str): A symbolic ref
    #    defer_prune (bool): Whether to defer pruning to the caller. NOTE:
    #                        The space won't be freed until you manually
    #                        call prune.
    #
    # Returns:
    #    (int|None) The amount of space pruned from the repository in
    #               Bytes, or None if defer_prune is True
    #
    def remove(self, ref, *, defer_prune=False):

        # Remove cache ref
        try:
            utils._remove_ref(os.path.join(self.casdir, 'refs', 'heads'), ref)
        except FileNotFoundError:
            raise CASCacheError("Could not find ref '{}'".format(ref))

        if not defer_prune:
            pruned = self.prune()
            return pruned

        return None

    # adds callback of iterator over reachable directory digests
    def add_reachable_directories_callback(self, callback):
        self.__reachable_directory_callbacks.append(callback)

    # adds callbacks of iterator over reachable file digests
    def add_reachable_digests_callback(self, callback):
        self.__reachable_digest_callbacks.append(callback)

    # prune():
    #
    # Prune unreachable objects from the repo.
    #
    def prune(self):
        ref_heads = os.path.join(self.casdir, 'refs', 'heads')

        pruned = 0
        reachable = set()

        # Check which objects are reachable
        for root, _, files in os.walk(ref_heads):
            for filename in files:
                ref_path = os.path.join(root, filename)
                ref = os.path.relpath(ref_path, ref_heads)

                tree = self.resolve_ref(ref)
                self._reachable_refs_dir(reachable, tree)

        # check callback directory digests that are reachable
        for digest_callback in self.__reachable_directory_callbacks:
            for digest in digest_callback():
                self._reachable_refs_dir(reachable, digest)

        # check callback file digests that are reachable
        for digest_callback in self.__reachable_digest_callbacks:
            for digest in digest_callback():
                reachable.add(digest.hash)

        # Prune unreachable objects
        for root, _, files in os.walk(os.path.join(self.casdir, 'objects')):
            for filename in files:
                objhash = os.path.basename(root) + filename
                if objhash not in reachable:
                    obj_path = os.path.join(root, filename)
                    pruned += os.stat(obj_path).st_size
                    os.unlink(obj_path)

        return pruned

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
    #     blobs (Digest): The directory digest
    #
    # Returns: List of missing Digest objects
    #
    def remote_missing_blobs(self, remote, blobs):
        missing_blobs = dict()
        # Limit size of FindMissingBlobs request
        for required_blobs_group in _grouper(blobs, 512):
            request = remote_execution_pb2.FindMissingBlobsRequest(instance_name=remote.spec.instance_name)

            for required_digest in required_blobs_group:
                d = request.blob_digests.add()
                d.CopyFrom(required_digest)

            response = remote.cas.FindMissingBlobs(request)
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

    def _refpath(self, ref):
        return os.path.join(self.casdir, 'refs', 'heads', ref)

    # _commit_directory():
    #
    # Adds local directory to content addressable store.
    #
    # Adds files, symbolic links and recursively other directories in
    # a local directory to the content addressable store.
    #
    # Args:
    #     path (str): Path to the directory to add.
    #     dir_digest (Digest): An optional Digest object to use.
    #
    # Returns:
    #     (Digest): Digest object for the directory added.
    #
    def _commit_directory(self, path, *, dir_digest=None):
        directory = remote_execution_pb2.Directory()

        for name in sorted(os.listdir(path)):
            full_path = os.path.join(path, name)
            mode = os.lstat(full_path).st_mode
            if stat.S_ISDIR(mode):
                dirnode = directory.directories.add()
                dirnode.name = name
                self._commit_directory(full_path, dir_digest=dirnode.digest)
            elif stat.S_ISREG(mode):
                filenode = directory.files.add()
                filenode.name = name
                self.add_object(path=full_path, digest=filenode.digest)
                filenode.is_executable = (mode & stat.S_IXUSR) == stat.S_IXUSR
            elif stat.S_ISLNK(mode):
                symlinknode = directory.symlinks.add()
                symlinknode.name = name
                symlinknode.target = os.readlink(full_path)
            elif stat.S_ISSOCK(mode):
                # The process serving the socket can't be cached anyway
                pass
            else:
                raise CASCacheError("Unsupported file type for {}".format(full_path))

        return self.add_object(digest=dir_digest,
                               buffer=directory.SerializeToString())

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

        with self._temporary_object() as f:
            remote._fetch_blob(digest, f)

            added_digest = self.add_object(path=f.name, link_directly=True)
            assert added_digest.hash == digest.hash

        return objpath

    def _batch_download_complete(self, batch, *, missing_blobs=None):
        for digest, data in batch.send(missing_blobs=missing_blobs):
            with self._temporary_object() as f:
                f.write(data)
                f.flush()

                added_digest = self.add_object(path=f.name, link_directly=True)
                assert added_digest.hash == digest.hash

    # Helper function for _fetch_directory().
    def _fetch_directory_batch(self, remote, batch, fetch_queue, fetch_next_queue):
        self._batch_download_complete(batch)

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
        elif (digest.size_bytes >= remote.max_batch_total_size_bytes or
              not remote.batch_read_supported):
            # Too large for batch request, download in independent request.
            self._ensure_blob(remote, digest)
            in_local_cache = True
        else:
            if not batch.add(digest):
                # Not enough space left in batch request.
                # Complete pending batch first.
                batch = self._fetch_directory_batch(remote, batch, fetch_queue, fetch_next_queue)
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
        # download but do not store the Tree object
        with utils._tempnamedfile(dir=self.tmpdir) as out:
            remote._fetch_blob(digest, out)

            tree = remote_execution_pb2.Tree()

            with open(out.name, 'rb') as f:
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

        batch = _CASBatchRead(remote)

        for digest in digests:
            if (digest.size_bytes >= remote.max_batch_total_size_bytes or
                    not remote.batch_read_supported):
                # Too large for batch request, download in independent request.
                try:
                    self._ensure_blob(remote, digest)
                except grpc.RpcError as e:
                    if e.code() == grpc.StatusCode.NOT_FOUND:
                        missing_blobs.append(digest)
                    else:
                        raise CASCacheError("Failed to fetch blob: {}".format(e)) from e
            else:
                if not batch.add(digest):
                    # Not enough space left in batch request.
                    # Complete pending batch first.
                    self._batch_download_complete(batch, missing_blobs=missing_blobs)

                    batch = _CASBatchRead(remote)
                    batch.add(digest)

        # Complete last pending batch
        self._batch_download_complete(batch, missing_blobs=missing_blobs)

        return missing_blobs

    # send_blobs():
    #
    # Upload blobs to remote CAS.
    #
    # Args:
    #    remote (CASRemote): The remote repository to upload to
    #    digests (list): The Digests of Blobs to upload
    #
    def send_blobs(self, remote, digests, u_uid=uuid.uuid4()):
        batch = _CASBatchUpdate(remote)

        for digest in digests:
            with open(self.objpath(digest), 'rb') as f:
                assert os.fstat(f.fileno()).st_size == digest.size_bytes

                if (digest.size_bytes >= remote.max_batch_total_size_bytes or
                        not remote.batch_update_supported):
                    # Too large for batch request, upload in independent request.
                    remote._send_blob(digest, f, u_uid=u_uid)
                else:
                    if not batch.add(digest, f):
                        # Not enough space left in batch request.
                        # Complete pending batch first.
                        batch.send()
                        batch = _CASBatchUpdate(remote)
                        batch.add(digest, f)

        # Send final batch
        batch.send()

    def _send_directory(self, remote, digest, u_uid=uuid.uuid4()):
        missing_blobs = self.remote_missing_blobs_for_directory(remote, digest)

        # Upload any blobs missing on the server
        self.send_blobs(remote, missing_blobs, u_uid)


class CASQuota:
    def __init__(self, context):
        self.context = context
        self.cas = context.get_cascache()
        self.casdir = self.cas.casdir
        self._config_cache_quota = context.config_cache_quota
        self._config_cache_quota_string = context.config_cache_quota_string
        self._cache_size = None               # The current cache size, sometimes it's an estimate
        self._cache_quota = None              # The cache quota
        self._cache_quota_original = None     # The cache quota as specified by the user, in bytes
        self._cache_quota_headroom = None     # The headroom in bytes before reaching the quota or full disk
        self._cache_lower_threshold = None    # The target cache size for a cleanup
        self.available_space = None

        self._message = context.message

        self._remove_callbacks = []   # Callbacks to remove unrequired refs and their remove method
        self._list_refs_callbacks = []  # Callbacks to all refs

        self._calculate_cache_quota()

    # compute_cache_size()
    #
    # Computes the real artifact cache size.
    #
    # Returns:
    #    (int): The size of the artifact cache.
    #
    def compute_cache_size(self):
        self._cache_size = utils._get_dir_size(self.casdir)
        return self._cache_size

    # get_cache_size()
    #
    # Fetches the cached size of the cache, this is sometimes
    # an estimate and periodically adjusted to the real size
    # when a cache size calculation job runs.
    #
    # When it is an estimate, the value is either correct, or
    # it is greater than the actual cache size.
    #
    # Returns:
    #     (int) An approximation of the artifact cache size, in bytes.
    #
    def get_cache_size(self):

        # If we don't currently have an estimate, figure out the real cache size.
        if self._cache_size is None:
            stored_size = self._read_cache_size()
            if stored_size is not None:
                self._cache_size = stored_size
            else:
                self.compute_cache_size()

        return self._cache_size

    # set_cache_size()
    #
    # Forcefully set the overall cache size.
    #
    # This is used to update the size in the main process after
    # having calculated in a cleanup or a cache size calculation job.
    #
    # Args:
    #     cache_size (int): The size to set.
    #     write_to_disk (bool): Whether to write the value to disk.
    #
    def set_cache_size(self, cache_size, *, write_to_disk=True):

        assert cache_size is not None

        self._cache_size = cache_size
        if write_to_disk:
            self._write_cache_size(self._cache_size)

    # full()
    #
    # Checks if the artifact cache is full, either
    # because the user configured quota has been exceeded
    # or because the underlying disk is almost full.
    #
    # Returns:
    #    (bool): True if the artifact cache is full
    #
    def full(self):

        if self.get_cache_size() > self._cache_quota:
            return True

        _, volume_avail = self._get_cache_volume_size()
        if volume_avail < self._cache_quota_headroom:
            return True

        return False

    # add_remove_callbacks()
    #
    # This adds tuples of iterators over unrequired objects (currently
    # artifacts and source refs), and a callback to remove them.
    #
    # Args:
    #    callback (iter(unrequired), remove): tuple of iterator and remove
    #        method associated.
    #
    def add_remove_callbacks(self, list_unrequired, remove_method):
        self._remove_callbacks.append((list_unrequired, remove_method))

    def add_list_refs_callback(self, list_callback):
        self._list_refs_callbacks.append(list_callback)

    ################################################
    #             Local Private Methods            #
    ################################################

    # _read_cache_size()
    #
    # Reads and returns the size of the artifact cache that's stored in the
    # cache's size file
    #
    # Returns:
    #    (int): The size of the artifact cache, as recorded in the file
    #
    def _read_cache_size(self):
        size_file_path = os.path.join(self.casdir, CACHE_SIZE_FILE)

        if not os.path.exists(size_file_path):
            return None

        with open(size_file_path, "r") as f:
            size = f.read()

        try:
            num_size = int(size)
        except ValueError as e:
            raise CASCacheError("Size '{}' parsed from '{}' was not an integer".format(
                size, size_file_path)) from e

        return num_size

    # _write_cache_size()
    #
    # Writes the given size of the artifact to the cache's size file
    #
    # Args:
    #    size (int): The size of the artifact cache to record
    #
    def _write_cache_size(self, size):
        assert isinstance(size, int)
        size_file_path = os.path.join(self.casdir, CACHE_SIZE_FILE)
        with utils.save_file_atomic(size_file_path, "w", tempdir=self.cas.tmpdir) as f:
            f.write(str(size))

    # _get_cache_volume_size()
    #
    # Get the available space and total space for the volume on
    # which the artifact cache is located.
    #
    # Returns:
    #    (int): The total number of bytes on the volume
    #    (int): The number of available bytes on the volume
    #
    # NOTE: We use this stub to allow the test cases
    #       to override what an artifact cache thinks
    #       about it's disk size and available bytes.
    #
    def _get_cache_volume_size(self):
        return utils._get_volume_size(self.casdir)

    # _calculate_cache_quota()
    #
    # Calculates and sets the cache quota and lower threshold based on the
    # quota set in Context.
    # It checks that the quota is both a valid expression, and that there is
    # enough disk space to satisfy that quota
    #
    def _calculate_cache_quota(self):
        # Headroom intended to give BuildStream a bit of leeway.
        # This acts as the minimum size of cache_quota and also
        # is taken from the user requested cache_quota.
        #
        if 'BST_TEST_SUITE' in os.environ:
            self._cache_quota_headroom = 0
        else:
            self._cache_quota_headroom = 2e9

        total_size, available_space = self._get_cache_volume_size()
        cache_size = self.get_cache_size()
        self.available_space = available_space

        # Ensure system has enough storage for the cache_quota
        #
        # If cache_quota is none, set it to the maximum it could possibly be.
        #
        # Also check that cache_quota is at least as large as our headroom.
        #
        cache_quota = self._config_cache_quota
        if cache_quota is None:
            # The user has set no limit, so we may take all the space.
            cache_quota = min(cache_size + available_space, total_size)
        if cache_quota < self._cache_quota_headroom:  # Check minimum
            raise LoadError(
                LoadErrorReason.INVALID_DATA,
                "Invalid cache quota ({}): BuildStream requires a minimum cache quota of {}.".format(
                    utils._pretty_size(cache_quota),
                    utils._pretty_size(self._cache_quota_headroom)))
        elif cache_quota > total_size:
            # A quota greater than the total disk size is certianly an error
            raise CASCacheError("Your system does not have enough available " +
                                "space to support the cache quota specified.",
                                detail=("You have specified a quota of {quota} total disk space.\n" +
                                        "The filesystem containing {local_cache_path} only " +
                                        "has {total_size} total disk space.")
                                .format(
                                    quota=self._config_cache_quota,
                                    local_cache_path=self.casdir,
                                    total_size=utils._pretty_size(total_size)),
                                reason='insufficient-storage-for-quota')

        elif cache_quota > cache_size + available_space:
            # The quota does not fit in the available space, this is a warning
            if '%' in self._config_cache_quota_string:
                available = (available_space / total_size) * 100
                available = '{}% of total disk space'.format(round(available, 1))
            else:
                available = utils._pretty_size(available_space)

            self._message(Message(
                None,
                MessageType.WARN,
                "Your system does not have enough available " +
                "space to support the cache quota specified.",
                detail=("You have specified a quota of {quota} total disk space.\n" +
                        "The filesystem containing {local_cache_path} only " +
                        "has {available_size} available.")
                .format(quota=self._config_cache_quota,
                        local_cache_path=self.casdir,
                        available_size=available)))

        # Place a slight headroom (2e9 (2GB) on the cache_quota) into
        # cache_quota to try and avoid exceptions.
        #
        # Of course, we might still end up running out during a build
        # if we end up writing more than 2G, but hey, this stuff is
        # already really fuzzy.
        #
        self._cache_quota_original = cache_quota
        self._cache_quota = cache_quota - self._cache_quota_headroom
        self._cache_lower_threshold = self._cache_quota / 2

    # clean():
    #
    # Clean the artifact cache as much as possible.
    #
    # Args:
    #    progress (callable): A callback to call when a ref is removed
    #
    # Returns:
    #    (int): The size of the cache after having cleaned up
    #
    def clean(self, progress=None):
        context = self.context

        # Some accumulative statistics
        removed_ref_count = 0
        space_saved = 0

        total_refs = 0
        for refs in self._list_refs_callbacks:
            total_refs += len(list(refs()))

        # Start off with an announcement with as much info as possible
        volume_size, volume_avail = self._get_cache_volume_size()
        self._message(Message(
            None, MessageType.STATUS, "Starting cache cleanup",
            detail=("Elements required by the current build plan:\n" + "{}\n" +
                    "User specified quota: {} ({})\n" +
                    "Cache usage: {}\n" +
                    "Cache volume: {} total, {} available")
            .format(
                total_refs,
                context.config_cache_quota,
                utils._pretty_size(self._cache_quota, dec_places=2),
                utils._pretty_size(self.get_cache_size(), dec_places=2),
                utils._pretty_size(volume_size, dec_places=2),
                utils._pretty_size(volume_avail, dec_places=2))))

        # Do a real computation of the cache size once, just in case
        self.compute_cache_size()
        usage = CASCacheUsage(self)
        self._message(Message(None, MessageType.STATUS,
                              "Cache usage recomputed: {}".format(usage)))

        # Collect digests and their remove method
        all_unrequired_refs = []
        for (unrequired_refs, remove) in self._remove_callbacks:
            for (mtime, ref) in unrequired_refs():
                all_unrequired_refs.append((mtime, ref, remove))

        # Pair refs and their remove method sorted in time order
        all_unrequired_refs = [(ref, remove) for (_, ref, remove) in sorted(all_unrequired_refs)]

        # Go through unrequired refs and remove them, oldest first
        made_space = False
        for (ref, remove) in all_unrequired_refs:
            size = remove(ref)
            removed_ref_count += 1
            space_saved += size

            self._message(Message(
                None, MessageType.STATUS,
                "Freed {: <7} {}".format(
                    utils._pretty_size(size, dec_places=2),
                    ref)))

            self.set_cache_size(self._cache_size - size)

            # User callback
            #
            # Currently this process is fairly slow, but we should
            # think about throttling this progress() callback if this
            # becomes too intense.
            if progress:
                progress()

            if self.get_cache_size() < self._cache_lower_threshold:
                made_space = True
                break

        if not made_space and self.full():
            # If too many artifacts are required, and we therefore
            # can't remove them, we have to abort the build.
            #
            # FIXME: Asking the user what to do may be neater
            #
            default_conf = os.path.join(os.environ['XDG_CONFIG_HOME'],
                                        'buildstream.conf')
            detail = ("Aborted after removing {} refs and saving {} disk space.\n"
                      "The remaining {} in the cache is required by the {} references in your build plan\n\n"
                      "There is not enough space to complete the build.\n"
                      "Please increase the cache-quota in {} and/or make more disk space."
                      .format(removed_ref_count,
                              utils._pretty_size(space_saved, dec_places=2),
                              utils._pretty_size(self.get_cache_size(), dec_places=2),
                              total_refs,
                              (context.config_origin or default_conf)))

            raise CASCacheError("Cache too full. Aborting.",
                                detail=detail,
                                reason="cache-too-full")

        # Informational message about the side effects of the cleanup
        self._message(Message(
            None, MessageType.INFO, "Cleanup completed",
            detail=("Removed {} refs and saving {} disk space.\n" +
                    "Cache usage is now: {}")
            .format(removed_ref_count,
                    utils._pretty_size(space_saved, dec_places=2),
                    utils._pretty_size(self.get_cache_size(), dec_places=2))))

        return self.get_cache_size()


def _grouper(iterable, n):
    while True:
        try:
            current = next(iterable)
        except StopIteration:
            return
        yield itertools.chain([current], itertools.islice(iterable, n - 1))
