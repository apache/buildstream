#!/usr/bin/env python3
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

from google.devtools.remoteexecution.v1test import remote_execution_pb2

from .. import utils
from .._exceptions import ArtifactError

from . import ArtifactCache


# A CASCache manages artifacts in a CAS repository as specified in the
# Remote Execution API.
#
# Args:
#     context (Context): The BuildStream context
#
class CASCache(ArtifactCache):

    def __init__(self, context):
        super().__init__(context)

        self.casdir = os.path.join(context.artifactdir, 'cas')
        os.makedirs(os.path.join(self.casdir, 'tmp'), exist_ok=True)

    ################################################
    #     Implementation of abstract methods       #
    ################################################
    def contains(self, element, key):
        refpath = self._refpath(self.get_artifact_fullname(element, key))

        # This assumes that the repository doesn't have any dangling pointers
        return os.path.exists(refpath)

    def extract(self, element, key):
        ref = self.get_artifact_fullname(element, key)

        tree = self.resolve_ref(ref)

        dest = os.path.join(self.extractdir, element._get_project().name, element.normal_name, tree.hash)
        if os.path.isdir(dest):
            # artifact has already been extracted
            return dest

        os.makedirs(self.extractdir, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix='tmp', dir=self.extractdir) as tmpdir:
            checkoutdir = os.path.join(tmpdir, ref)
            self._checkout(checkoutdir, tree)

            os.makedirs(os.path.dirname(dest), exist_ok=True)
            try:
                os.rename(checkoutdir, dest)
            except OSError as e:
                # With rename it's possible to get either ENOTEMPTY or EEXIST
                # in the case that the destination path is a not empty directory.
                #
                # If rename fails with these errors, another process beat
                # us to it so just ignore.
                if e.errno not in [os.errno.ENOTEMPTY, os.errno.EEXIST]:
                    raise ArtifactError("Failed to extract artifact for ref '{}': {}"
                                        .format(ref, e)) from e

        return dest

    def commit(self, element, content, keys):
        refs = [self.get_artifact_fullname(element, key) for key in keys]

        tree = self._create_tree(content)

        for ref in refs:
            self.set_ref(ref, tree)

    def can_diff(self):
        return True

    def diff(self, element, key_a, key_b, *, subdir=None):
        ref_a = self.get_artifact_fullname(element, key_a)
        ref_b = self.get_artifact_fullname(element, key_b)

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

    ################################################
    #                API Private Methods           #
    ################################################

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
    #
    # Returns:
    #     (Digest): The digest of the added object
    #
    # Either `path` or `buffer` must be passed, but not both.
    #
    def add_object(self, *, digest=None, path=None, buffer=None):
        # Exactly one of the two parameters has to be specified
        assert (path is None) != (buffer is None)

        if digest is None:
            digest = remote_execution_pb2.Digest()

        try:
            h = hashlib.sha256()
            # Always write out new file to avoid corruption if input file is modified
            with tempfile.NamedTemporaryFile(dir=os.path.join(self.casdir, 'tmp')) as out:
                if path:
                    with open(path, 'rb') as f:
                        for chunk in iter(lambda: f.read(4096), b""):
                            h.update(chunk)
                            out.write(chunk)
                else:
                    h.update(buffer)
                    out.write(buffer)

                out.flush()

                digest.hash = h.hexdigest()
                digest.size_bytes = os.fstat(out.fileno()).st_size

                # Place file at final location
                objpath = self.objpath(digest)
                os.makedirs(os.path.dirname(objpath), exist_ok=True)
                os.link(out.name, objpath)

        except FileExistsError as e:
            # We can ignore the failed link() if the object is already in the repo.
            pass

        except OSError as e:
            raise ArtifactError("Failed to hash object: {}".format(e)) from e

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
        with utils.save_file_atomic(refpath, 'wb') as f:
            f.write(tree.SerializeToString())

    # resolve_ref():
    #
    # Resolve a ref to a digest.
    #
    # Args:
    #     ref (str): The name of the ref
    #
    # Returns:
    #     (Digest): The digest stored in the ref
    #
    def resolve_ref(self, ref):
        refpath = self._refpath(ref)

        try:
            with open(refpath, 'rb') as f:
                digest = remote_execution_pb2.Digest()
                digest.ParseFromString(f.read())
                return digest

        except FileNotFoundError as e:
            raise ArtifactError("Attempt to access unavailable artifact: {}".format(e)) from e

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
                os.chmod(fullpath, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP |
                         stat.S_IROTH | stat.S_IXOTH)

        for dirnode in directory.directories:
            fullpath = os.path.join(dest, dirnode.name)
            self._checkout(fullpath, dirnode.digest)

        for symlinknode in directory.symlinks:
            # symlink
            fullpath = os.path.join(dest, symlinknode.name)
            os.symlink(symlinknode.target, fullpath)

    def _refpath(self, ref):
        return os.path.join(self.casdir, 'refs', 'heads', ref)

    def _create_tree(self, path, *, digest=None):
        directory = remote_execution_pb2.Directory()

        for name in sorted(os.listdir(path)):
            full_path = os.path.join(path, name)
            mode = os.lstat(full_path).st_mode
            if stat.S_ISDIR(mode):
                dirnode = directory.directories.add()
                dirnode.name = name
                self._create_tree(full_path, digest=dirnode.digest)
            elif stat.S_ISREG(mode):
                filenode = directory.files.add()
                filenode.name = name
                self.add_object(path=full_path, digest=filenode.digest)
                filenode.is_executable = (mode & stat.S_IXUSR) == stat.S_IXUSR
            elif stat.S_ISLNK(mode):
                symlinknode = directory.symlinks.add()
                symlinknode.name = name
                symlinknode.target = os.readlink(full_path)
            else:
                raise ArtifactError("Unsupported file type for {}".format(full_path))

        return self.add_object(digest=digest, buffer=directory.SerializeToString())

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

        raise ArtifactError("Subdirectory {} not found".format(name))

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
