#
#  Copyright (C) 2018 Bloomberg LP
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
#        Jim MacArthur <jim.macarthur@codethink.co.uk>

"""
CasBasedDirectory
=========

Implementation of the Directory class which backs onto a Merkle-tree based content
addressable storage system.

See also: :ref:`sandboxing`.
"""

import os
import stat
import tarfile as tarfilelib
from io import StringIO

from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from .directory import Directory, VirtualDirectoryError, _FileType
from ._filebaseddirectory import FileBasedDirectory
from ..utils import FileListResult, BST_ARBITRARY_TIMESTAMP


class IndexEntry:
    """ Directory entry used in CasBasedDirectory.index """

    def __init__(
        self,
        name,
        entrytype,
        *,
        digest=None,
        target=None,
        is_executable=False,
        buildstream_object=None,
        modified=False
    ):
        self.name = name
        self.type = entrytype
        self.digest = digest
        self.target = target
        self.is_executable = is_executable
        self.buildstream_object = buildstream_object
        self.modified = modified

    def get_directory(self, parent):
        if not self.buildstream_object:
            self.buildstream_object = CasBasedDirectory(
                parent.cas_cache, digest=self.digest, parent=parent, filename=self.name
            )
            self.digest = None

        return self.buildstream_object

    def get_digest(self):
        if self.digest:
            return self.digest
        else:
            return self.buildstream_object._get_digest()


# CasBasedDirectory intentionally doesn't call its superclass constuctor,
# which is meant to be unimplemented.
# pylint: disable=super-init-not-called


class CasBasedDirectory(Directory):
    """
    CAS-based directories can have two names; one is a 'common name' which has no effect
    on functionality, and the 'filename'. If a CasBasedDirectory has a parent, then 'filename'
    must be the name of an entry in the parent directory's index which points to this object.
    This is used to inform a parent directory that it must update the given hash for this
    object when this object changes.

    Typically a top-level CasBasedDirectory will have a common_name and no filename, and
    subdirectories wil have a filename and no common_name. common_name can used to identify
    CasBasedDirectory objects in a log file, since they have no unique position in a file
    system.
    """

    # Two constants which define the separators used by the remote execution API.
    _pb2_path_sep = "/"
    _pb2_absolute_path_prefix = "/"

    def __init__(self, cas_cache, *, digest=None, parent=None, common_name="untitled", filename=None):
        self.filename = filename
        self.common_name = common_name
        self.cas_cache = cas_cache
        self.__digest = None
        self.index = {}
        self.parent = parent
        self._reset(digest=digest)

    def _reset(self, *, digest=None):
        self.__digest = digest
        self.index = {}
        if digest:
            self._populate_index(digest)

    def _populate_index(self, digest):
        try:
            pb2_directory = remote_execution_pb2.Directory()
            with open(self.cas_cache.objpath(digest), "rb") as f:
                pb2_directory.ParseFromString(f.read())
        except FileNotFoundError as e:
            raise VirtualDirectoryError("Directory not found in local cache: {}".format(e)) from e

        for entry in pb2_directory.directories:
            self.index[entry.name] = IndexEntry(entry.name, _FileType.DIRECTORY, digest=entry.digest)
        for entry in pb2_directory.files:
            self.index[entry.name] = IndexEntry(
                entry.name, _FileType.REGULAR_FILE, digest=entry.digest, is_executable=entry.is_executable
            )
        for entry in pb2_directory.symlinks:
            self.index[entry.name] = IndexEntry(entry.name, _FileType.SYMLINK, target=entry.target)

    def _find_self_in_parent(self):
        assert self.parent is not None
        parent = self.parent
        for (k, v) in parent.index.items():
            if v.buildstream_object == self:
                return k
        return None

    def _add_directory(self, name):
        assert name not in self.index

        newdir = CasBasedDirectory(self.cas_cache, parent=self, filename=name)

        self.index[name] = IndexEntry(name, _FileType.DIRECTORY, buildstream_object=newdir)

        self.__invalidate_digest()

        return newdir

    def _add_file(self, basename, filename, modified=False, can_link=False):
        entry = IndexEntry(filename, _FileType.REGULAR_FILE, modified=modified or filename in self.index)
        path = os.path.join(basename, filename)
        entry.digest = self.cas_cache.add_object(path=path, link_directly=can_link)
        entry.is_executable = os.access(path, os.X_OK)
        self.index[filename] = entry

        self.__invalidate_digest()

    def _add_new_link_direct(self, name, target):
        self.index[name] = IndexEntry(name, _FileType.SYMLINK, target=target, modified=name in self.index)

        self.__invalidate_digest()

    def delete_entry(self, name):
        if name in self.index:
            del self.index[name]

        self.__invalidate_digest()

    def find_root(self):
        """ Finds the root of this directory tree by following 'parent' until there is
        no parent. """
        if self.parent:
            return self.parent.find_root()
        else:
            return self

    def descend(self, *paths, create=False, follow_symlinks=False):
        """Descend one or more levels of directory hierarchy and return a new
        Directory object for that directory.

        Arguments:
        * *paths (str): A list of strings which are all directory names.
        * create (boolean): If this is true, the directories will be created if
          they don't already exist.

        Note: At the moment, creating a directory by descending does
        not update this object in the CAS cache. However, performing
        an import_files() into a subdirectory of any depth obtained by
        descending from this object *will* cause this directory to be
        updated and stored.

        """

        current_dir = self
        paths = list(paths)

        for path in paths:
            # Skip empty path segments
            if not path:
                continue

            entry = current_dir.index.get(path)

            if entry:
                if entry.type == _FileType.DIRECTORY:
                    current_dir = entry.get_directory(current_dir)
                elif follow_symlinks and entry.type == _FileType.SYMLINK:
                    linklocation = entry.target
                    newpaths = linklocation.split(os.path.sep)
                    if os.path.isabs(linklocation):
                        current_dir = current_dir.find_root().descend(*newpaths, follow_symlinks=True)
                    else:
                        current_dir = current_dir.descend(*newpaths, follow_symlinks=True)
                else:
                    error = "Cannot descend into {}, which is a '{}' in the directory {}"
                    raise VirtualDirectoryError(
                        error.format(path, current_dir.index[path].type, current_dir), reason="not-a-directory"
                    )
            else:
                if path == ".":
                    continue
                if path == "..":
                    if current_dir.parent is not None:
                        current_dir = current_dir.parent
                    # In POSIX /.. == / so just stay at the root dir
                    continue
                if create:
                    current_dir = current_dir._add_directory(path)
                else:
                    error = "'{}' not found in {}"
                    raise VirtualDirectoryError(error.format(path, str(current_dir)), reason="directory-not-found")

        return current_dir

    def _check_replacement(self, name, relative_pathname, fileListResult):
        """ Checks whether 'name' exists, and if so, whether we can overwrite it.
        If we can, add the name to 'overwritten_files' and delete the existing entry.
        Returns 'True' if the import should go ahead.
        fileListResult.overwritten and fileListResult.ignore are updated depending
        on the result. """
        existing_entry = self.index.get(name)
        if existing_entry is None:
            return True
        elif existing_entry.type == _FileType.DIRECTORY:
            # If 'name' maps to a DirectoryNode, then there must be an entry in index
            # pointing to another Directory.
            subdir = existing_entry.get_directory(self)
            if subdir.is_empty():
                self.delete_entry(name)
                fileListResult.overwritten.append(relative_pathname)
                return True
            else:
                # We can't overwrite a non-empty directory, so we just ignore it.
                fileListResult.ignored.append(relative_pathname)
                return False
        else:
            self.delete_entry(name)
            fileListResult.overwritten.append(relative_pathname)
            return True

    def _partial_import_cas_into_cas(self, source_directory, filter_callback, *, path_prefix="", origin=None, result):
        """ Import files from a CAS-based directory. """
        if origin is None:
            origin = self

        for name, entry in source_directory.index.items():
            # The destination filename, relative to the root where the import started
            relative_pathname = os.path.join(path_prefix, name)

            is_dir = entry.type == _FileType.DIRECTORY

            if is_dir:
                create_subdir = name not in self.index

                if create_subdir and not filter_callback:
                    # If subdirectory does not exist yet and there is no filter,
                    # we can import the whole source directory by digest instead
                    # of importing each directory entry individually.
                    subdir_digest = entry.get_digest()
                    dest_entry = IndexEntry(name, _FileType.DIRECTORY, digest=subdir_digest)
                    self.index[name] = dest_entry
                    self.__invalidate_digest()

                    # However, we still need to iterate over the directory entries
                    # to fill in `result.files_written`.

                    # Use source subdirectory object if it already exists,
                    # otherwise create object for destination subdirectory.
                    # This is based on the assumption that the destination
                    # subdirectory is more likely to be modified later on
                    # (e.g., by further import_files() calls).
                    if entry.buildstream_object:
                        subdir = entry.buildstream_object
                    else:
                        subdir = dest_entry.get_directory(self)

                    subdir.__add_files_to_result(path_prefix=relative_pathname, result=result)
                else:
                    src_subdir = source_directory.descend(name)
                    if src_subdir == origin:
                        continue

                    try:
                        dest_subdir = self.descend(name, create=create_subdir)
                    except VirtualDirectoryError:
                        filetype = self.index[name].type
                        raise VirtualDirectoryError(
                            "Destination is a {}, not a directory: /{}".format(filetype, relative_pathname)
                        )

                    dest_subdir._partial_import_cas_into_cas(
                        src_subdir, filter_callback, path_prefix=relative_pathname, origin=origin, result=result
                    )

            if filter_callback and not filter_callback(relative_pathname):
                if is_dir and create_subdir and dest_subdir.is_empty():
                    # Complete subdirectory has been filtered out, remove it
                    self.delete_entry(name)

                # Entry filtered out, move to next
                continue

            if not is_dir:
                if self._check_replacement(name, relative_pathname, result):
                    if entry.type == _FileType.REGULAR_FILE:
                        self.index[name] = IndexEntry(
                            name,
                            _FileType.REGULAR_FILE,
                            digest=entry.digest,
                            is_executable=entry.is_executable,
                            modified=True,
                        )
                        self.__invalidate_digest()
                    else:
                        assert entry.type == _FileType.SYMLINK
                        self._add_new_link_direct(name=name, target=entry.target)
                    result.files_written.append(relative_pathname)

    def import_files(
        self, external_pathspec, *, filter_callback=None, report_written=True, update_mtime=False, can_link=False
    ):
        """ See superclass Directory for arguments """

        result = FileListResult()

        if isinstance(external_pathspec, FileBasedDirectory):
            external_pathspec = external_pathspec._get_underlying_directory()

        if isinstance(external_pathspec, str):
            # Import files from local filesystem by first importing complete
            # directory into CAS (using buildbox-casd) and then importing its
            # content into this CasBasedDirectory using CAS-to-CAS import
            # to write the report, handle possible conflicts (if the target
            # directory is not empty) and apply the optional filter.
            digest = self.cas_cache.import_directory(external_pathspec)
            external_pathspec = CasBasedDirectory(self.cas_cache, digest=digest)

        assert isinstance(external_pathspec, CasBasedDirectory)
        self._partial_import_cas_into_cas(external_pathspec, filter_callback, result=result)

        # TODO: No notice is taken of report_written or update_mtime.
        # Current behaviour is to fully populate the report, which is inefficient,
        # but still correct.

        return result

    def import_single_file(self, external_pathspec):
        result = FileListResult()
        if self._check_replacement(os.path.basename(external_pathspec), os.path.dirname(external_pathspec), result):
            self._add_file(
                os.path.dirname(external_pathspec),
                os.path.basename(external_pathspec),
                modified=os.path.basename(external_pathspec) in result.overwritten,
            )
            result.files_written.append(external_pathspec)
        return result

    def set_deterministic_mtime(self):
        """ Sets a static modification time for all regular files in this directory.
        Since we don't store any modification time, we don't need to do anything.
        """

    def set_deterministic_user(self):
        """ Sets all files in this directory to the current user's euid/egid.
        We also don't store user data, so this can be ignored.
        """

    def export_files(self, to_directory, *, can_link=False, can_destroy=False):
        """Copies everything from this into to_directory, which must be the name
        of a traditional filesystem directory.

        Arguments:

        to_directory (string): a path outside this directory object
        where the contents will be copied to.

        can_link (bool): Whether we can create hard links in to_directory
        instead of copying.

        can_destroy (bool): Whether we can destroy elements in this
        directory to export them (e.g. by renaming them as the
        target).

        """

        self.cas_cache.checkout(to_directory, self._get_digest(), can_link=can_link)

    def export_to_tar(self, tarfile, destination_dir, mtime=BST_ARBITRARY_TIMESTAMP):
        for filename, entry in self.index.items():
            arcname = os.path.join(destination_dir, filename)
            if entry.type == _FileType.DIRECTORY:
                tarinfo = tarfilelib.TarInfo(arcname)
                tarinfo.mtime = mtime
                tarinfo.type = tarfilelib.DIRTYPE
                tarinfo.mode = 0o755
                tarfile.addfile(tarinfo)
                self.descend(filename).export_to_tar(tarfile, arcname, mtime)
            elif entry.type == _FileType.REGULAR_FILE:
                source_name = self.cas_cache.objpath(entry.digest)
                tarinfo = tarfilelib.TarInfo(arcname)
                tarinfo.mtime = mtime
                tarinfo.mode |= entry.is_executable & stat.S_IXUSR
                tarinfo.size = os.path.getsize(source_name)
                with open(source_name, "rb") as f:
                    tarfile.addfile(tarinfo, f)
            elif entry.type == _FileType.SYMLINK:
                tarinfo = tarfilelib.TarInfo(arcname)
                tarinfo.mtime = mtime
                tarinfo.mode |= entry.is_executable & stat.S_IXUSR
                tarinfo.linkname = entry.target
                tarinfo.type = tarfilelib.SYMTYPE
                f = StringIO(entry.target)
                tarfile.addfile(tarinfo, f)
            else:
                raise VirtualDirectoryError("can not export file type {} to tar".format(entry.type))

    def _mark_changed(self):
        """ It should not be possible to externally modify a CAS-based
        directory at the moment."""
        raise NotImplementedError()

    def is_empty(self):
        """ Return true if this directory has no files, subdirectories or links in it.
        """
        return len(self.index) == 0

    def _mark_directory_unmodified(self):
        # Marks all entries in this directory and all child directories as unmodified.
        for i in self.index.values():
            i.modified = False
            if i.type == _FileType.DIRECTORY and i.buildstream_object:
                i.buildstream_object._mark_directory_unmodified()

    def _mark_entry_unmodified(self, name):
        # Marks an entry as unmodified. If the entry is a directory, it will
        # recursively mark all its tree as unmodified.
        self.index[name].modified = False
        if self.index[name].buildstream_object:
            self.index[name].buildstream_object._mark_directory_unmodified()

    def mark_unmodified(self):
        """ Marks all files in this directory (recursively) as unmodified.
        If we have a parent, we mark our own entry as unmodified in that parent's
        index.
        """
        if self.parent:
            self.parent._mark_entry_unmodified(self._find_self_in_parent())
        else:
            self._mark_directory_unmodified()

    def _lightweight_resolve_to_index(self, path):
        """A lightweight function for transforming paths into IndexEntry
        objects. This does not follow symlinks.

        path: The string to resolve. This should be a series of path
        components separated by the protocol buffer path separator
        _pb2_path_sep.

        Returns: the IndexEntry found, or None if any of the path components were not present.

        """
        directory = self
        path_components = path.split(CasBasedDirectory._pb2_path_sep)
        for component in path_components[:-1]:
            if component not in directory.index:
                return None
            if directory.index[component].type == _FileType.DIRECTORY:
                directory = directory.index[component].get_directory(self)
            else:
                return None
        return directory.index.get(path_components[-1], None)

    def list_modified_paths(self):
        """Provide a list of relative paths which have been modified since the
        last call to mark_unmodified.

        Return value: List(str) - list of modified paths
        """

        for p in self.list_relative_paths():
            i = self._lightweight_resolve_to_index(p)
            if i and i.modified:
                yield p

    def list_relative_paths(self):
        """Provide a list of all relative paths.

        Yields:
          (List(str)) - list of all files with relative paths.

        """
        yield from self._list_prefixed_relative_paths()

    def _list_prefixed_relative_paths(self, prefix=""):
        """Provide a list of all relative paths.

        Arguments:
          prefix (str): an optional prefix to the relative paths, this is
                        also emitted by itself.

        Yields:
          (List(str)) - list of all files with relative paths.

        """

        file_list = list(filter(lambda i: i[1].type != _FileType.DIRECTORY, self.index.items()))
        directory_list = filter(lambda i: i[1].type == _FileType.DIRECTORY, self.index.items())

        if prefix != "":
            yield prefix

        for (k, v) in sorted(file_list):
            yield os.path.join(prefix, k)

        for (k, v) in sorted(directory_list):
            subdir = v.get_directory(self)
            yield from subdir._list_prefixed_relative_paths(prefix=os.path.join(prefix, k))

    def walk(self):
        """Provide a list of dictionaries containing information about the files.

        Yields:
          info (dict) - a dictionary containing name, type and size of the files.

        """
        yield from self._walk()

    def _walk(self, prefix=""):
        """ Walk through the files, collecting the required data

        Arguments:
          prefix (str): an optional prefix to the relative paths, this is
                        also emitted by itself.

        Yields:
          info (dict) - a dictionary containing name, type and size of the files.

          """
        for leaf in sorted(self.index.keys()):
            entry = self.index[leaf]
            info = {"name": os.path.join(prefix, leaf), "type": entry.type}
            if entry.type == _FileType.REGULAR_FILE:
                info["executable"] = entry.is_executable
                info["size"] = self.get_size()
            elif entry.type == _FileType.SYMLINK:
                info["target"] = entry.target
                info["size"] = len(entry.target)
            if entry.type == _FileType.DIRECTORY:
                directory = entry.get_directory(self)
                info["size"] = len(directory.index)
                yield info
                yield from directory._walk(os.path.join(prefix, leaf))
            else:
                yield info

    def get_size(self):
        digest = self._get_digest()
        total = digest.size_bytes
        for i in self.index.values():
            if i.type == _FileType.DIRECTORY:
                subdir = i.get_directory(self)
                total += subdir.get_size()
            elif i.type == _FileType.REGULAR_FILE:
                total += i.digest.size_bytes
            # Symlink nodes are encoded as part of the directory serialization.
        return total

    def _get_identifier(self):
        path = ""
        if self.parent:
            path = self.parent._get_identifier()
        if self.filename:
            path += "/" + self.filename
        else:
            path += "/" + self.common_name
        return path

    def __str__(self):
        return "[CAS:{}]".format(self._get_identifier())

    def _get_underlying_directory(self):
        """ There is no underlying directory for a CAS-backed directory, so
        throw an exception. """
        raise VirtualDirectoryError(
            "_get_underlying_directory was called on a CAS-backed directory," + " which has no underlying directory."
        )

    # _get_digest():
    #
    # Return the Digest for this directory.
    #
    # Returns:
    #   (Digest): The Digest protobuf object for the Directory protobuf
    #
    def _get_digest(self):
        if not self.__digest:
            # Create updated Directory proto
            pb2_directory = remote_execution_pb2.Directory()

            for name, entry in sorted(self.index.items()):
                if entry.type == _FileType.DIRECTORY:
                    dirnode = pb2_directory.directories.add()
                    dirnode.name = name

                    # Update digests for subdirectories in DirectoryNodes.
                    # No need to call entry.get_directory().
                    # If it hasn't been instantiated, digest must be up-to-date.
                    subdir = entry.buildstream_object
                    if subdir:
                        dirnode.digest.CopyFrom(subdir._get_digest())
                    else:
                        dirnode.digest.CopyFrom(entry.digest)
                elif entry.type == _FileType.REGULAR_FILE:
                    filenode = pb2_directory.files.add()
                    filenode.name = name
                    filenode.digest.CopyFrom(entry.digest)
                    filenode.is_executable = entry.is_executable
                elif entry.type == _FileType.SYMLINK:
                    symlinknode = pb2_directory.symlinks.add()
                    symlinknode.name = name
                    symlinknode.target = entry.target

            self.__digest = self.cas_cache.add_object(buffer=pb2_directory.SerializeToString())

        return self.__digest

    def _exists(self, *path, follow_symlinks=False):
        try:
            subdir = self.descend(*path[:-1], follow_symlinks=follow_symlinks)
            target = subdir.index.get(path[-1])
            if target is not None:
                if target.type == _FileType.REGULAR_FILE:
                    return True
                elif follow_symlinks and target.type == _FileType.SYMLINK:
                    linklocation = target.target
                    newpath = linklocation.split(os.path.sep)
                    if os.path.isabs(linklocation):
                        return subdir.find_root()._exists(*newpath, follow_symlinks=True)
                    return subdir._exists(*newpath, follow_symlinks=True)
            return False
        except VirtualDirectoryError:
            return False

    def __invalidate_digest(self):
        if self.__digest:
            self.__digest = None
            if self.parent:
                self.parent.__invalidate_digest()

    def __add_files_to_result(self, *, path_prefix="", result):
        for name, entry in self.index.items():
            # The destination filename, relative to the root where the import started
            relative_pathname = os.path.join(path_prefix, name)

            if entry.type == _FileType.DIRECTORY:
                subdir = self.descend(name)
                subdir.__add_files_to_result(path_prefix=relative_pathname, result=result)
            else:
                result.files_written.append(relative_pathname)
