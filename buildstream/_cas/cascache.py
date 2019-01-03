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
import os
import stat
import tempfile
import contextlib

from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2

from .. import utils
from .._exceptions import CASCacheError


# A CASCache manages a CAS repository as specified in the Remote Execution API.
#
# Args:
#     path (str): The root directory for the CAS repository
#
class CASCache():

    def __init__(self, path):
        self.casdir = os.path.join(path, 'cas')
        self.tmpdir = os.path.join(path, 'tmp')
        os.makedirs(os.path.join(self.casdir, 'refs', 'heads'), exist_ok=True)
        os.makedirs(os.path.join(self.casdir, 'objects'), exist_ok=True)
        os.makedirs(self.tmpdir, exist_ok=True)

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
    #
    # Returns: True if the subdir exists & is populated in the cache, False otherwise
    #
    def contains_subdir_artifact(self, ref, subdir):
        tree = self.resolve_ref(ref)

        # This assumes that the subdir digest is present in the element tree
        subdirdigest = self._get_subdir(tree, subdir)
        objpath = self.objpath(subdirdigest)

        # True if subdir content is cached or if empty as expected
        return os.path.exists(objpath)

    # extract():
    #
    # Extract cached directory for the specified ref if it hasn't
    # already been extracted.
    #
    # Args:
    #     ref (str): The ref whose directory to extract
    #     path (str): The destination path
    #     subdir (str): Optional specific dir to extract
    #
    # Raises:
    #     CASCacheError: In cases there was an OSError, or if the ref did not exist.
    #
    # Returns: path to extracted directory
    #
    def extract(self, ref, path, subdir=None):
        tree = self.resolve_ref(ref, update_mtime=True)

        originaldest = dest = os.path.join(path, tree.hash)

        # If artifact is already extracted, check if the optional subdir
        # has also been extracted. If the artifact has not been extracted
        # a full extraction would include the optional subdir
        if os.path.isdir(dest):
            if subdir:
                if not os.path.isdir(os.path.join(dest, subdir)):
                    dest = os.path.join(dest, subdir)
                    tree = self._get_subdir(tree, subdir)
                else:
                    return dest
            else:
                return dest

        with tempfile.TemporaryDirectory(prefix='tmp', dir=self.tmpdir) as tmpdir:
            checkoutdir = os.path.join(tmpdir, ref)
            self._checkout(checkoutdir, tree)

            try:
                utils.move_atomic(checkoutdir, dest)
            except utils.DirectoryExistsError:
                # Another process beat us to rename
                pass
            except OSError as e:
                raise CASCacheError("Failed to extract directory for ref '{}': {}".format(ref, e)) from e

        return originaldest

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
    def diff(self, ref_a, ref_b, *, subdir=None):
        tree_a = self.resolve_ref(ref_a)
        tree_b = self.resolve_ref(ref_b)

        if subdir:
            tree_a = self._get_subdir(tree_a, subdir)
            tree_b = self._get_subdir(tree_b, subdir)

        added = []
        removed = []
        modified = []

        self._diff_trees(tree_a, tree_b, added=added, removed=removed, modified=modified)

        return modified, removed, added

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
                    for chunk in iter(lambda: tmp.read(4096), b""):
                        h.update(chunk)
                else:
                    tmp = stack.enter_context(tempfile.NamedTemporaryFile(dir=self.tmpdir))
                    # Set mode bits to 0644
                    os.chmod(tmp.name, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)

                    if path:
                        with open(path, 'rb') as f:
                            for chunk in iter(lambda: f.read(4096), b""):
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

    # calculate_cache_size()
    #
    # Return the real disk usage of the CAS cache.
    #
    # Returns:
    #    (int): The size of the cache.
    #
    def calculate_cache_size(self):
        return utils._get_dir_size(self.casdir)

    # list_refs():
    #
    # List refs in Least Recently Modified (LRM) order.
    #
    # Returns:
    #     (list) - A list of refs in LRM order
    #
    def list_refs(self):
        # string of: /path/to/repo/refs/heads
        ref_heads = os.path.join(self.casdir, 'refs', 'heads')

        refs = []
        mtimes = []

        for root, _, files in os.walk(ref_heads):
            for filename in files:
                ref_path = os.path.join(root, filename)
                refs.append(os.path.relpath(ref_path, ref_heads))
                # Obtain the mtime (the time a file was last modified)
                mtimes.append(os.path.getmtime(ref_path))

        # NOTE: Sorted will sort from earliest to latest, thus the
        # first ref of this list will be the file modified earliest.
        return [ref for _, ref in sorted(zip(mtimes, refs))]

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
        refpath = self._refpath(ref)
        if not os.path.exists(refpath):
            raise CASCacheError("Could not find ref '{}'".format(ref))

        os.unlink(refpath)

        if not defer_prune:
            pruned = self.prune()
            return pruned

        return None

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

    # Check to see if a blob is in the local CAS
    # return None if not
    def check_blob(self, digest):
        objpath = self.objpath(digest)
        if os.path.exists(objpath):
            # already in local repository
            return objpath
        else:
            return None

    def yield_directory_digests(self, directory_digest):
        # parse directory, and recursively add blobs
        d = remote_execution_pb2.Digest()
        d.hash = directory_digest.hash
        d.size_bytes = directory_digest.size_bytes
        yield d

        directory = remote_execution_pb2.Directory()

        with open(self.objpath(directory_digest), 'rb') as f:
            directory.ParseFromString(f.read())

        for filenode in directory.files:
            d = remote_execution_pb2.Digest()
            d.hash = filenode.digest.hash
            d.size_bytes = filenode.digest.size_bytes
            yield d

        for dirnode in directory.directories:
            yield from self.yield_directory_digests(dirnode.digest)

    ################################################
    #             Local Private Methods            #
    ################################################

    def _checkout(self, dest, tree):
        os.makedirs(dest, exist_ok=True)

        directory = remote_execution_pb2.Directory()

        with open(self.objpath(tree), 'rb') as f:
            directory.ParseFromString(f.read())

        for filenode in directory.files:
            # regular file, create hardlink
            fullpath = os.path.join(dest, filenode.name)
            os.link(self.objpath(filenode.digest), fullpath)

            if filenode.is_executable:
                os.chmod(fullpath, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR |
                         stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

        for dirnode in directory.directories:
            # Don't try to checkout a dangling ref
            if os.path.exists(self.objpath(dirnode.digest)):
                fullpath = os.path.join(dest, dirnode.name)
                self._checkout(fullpath, dirnode.digest)

        for symlinknode in directory.symlinks:
            # symlink
            fullpath = os.path.join(dest, symlinknode.name)
            os.symlink(symlinknode.target, fullpath)

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

    def _diff_trees(self, tree_a, tree_b, *, added, removed, modified, path=""):
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
                self._diff_trees(None, dir_b.directories[b].digest,
                                 added=added, removed=removed, modified=modified,
                                 path=os.path.join(path, dir_b.directories[b].name))
                b += 1
            elif a < len(dir_a.directories) and (b >= len(dir_b.directories) or
                                                 dir_b.directories[b].name > dir_a.directories[a].name):
                self._diff_trees(dir_a.directories[a].digest, None,
                                 added=added, removed=removed, modified=modified,
                                 path=os.path.join(path, dir_a.directories[a].name))
                a += 1
            else:
                # Subdirectory exists in both directories
                if dir_a.directories[a].digest.hash != dir_b.directories[b].digest.hash:
                    self._diff_trees(dir_a.directories[a].digest, dir_b.directories[b].digest,
                                     added=added, removed=removed, modified=modified,
                                     path=os.path.join(path, dir_a.directories[a].name))
                a += 1
                b += 1

    def _reachable_refs_dir(self, reachable, tree, update_mtime=False):
        if tree.hash in reachable:
            return

        if update_mtime:
            os.utime(self.objpath(tree))

        reachable.add(tree.hash)

        directory = remote_execution_pb2.Directory()

        with open(self.objpath(tree), 'rb') as f:
            directory.ParseFromString(f.read())

        for filenode in directory.files:
            if update_mtime:
                os.utime(self.objpath(filenode.digest))
            reachable.add(filenode.digest.hash)

        for dirnode in directory.directories:
            self._reachable_refs_dir(reachable, dirnode.digest, update_mtime=update_mtime)

    def _required_blobs(self, directory_digest):
        # parse directory, and recursively add blobs
        d = remote_execution_pb2.Digest()
        d.hash = directory_digest.hash
        d.size_bytes = directory_digest.size_bytes
        yield d

        directory = remote_execution_pb2.Directory()

        with open(self.objpath(directory_digest), 'rb') as f:
            directory.ParseFromString(f.read())

        for filenode in directory.files:
            d = remote_execution_pb2.Digest()
            d.hash = filenode.digest.hash
            d.size_bytes = filenode.digest.size_bytes
            yield d

        for dirnode in directory.directories:
            yield from self._required_blobs(dirnode.digest)
