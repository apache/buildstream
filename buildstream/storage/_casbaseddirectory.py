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

from collections import OrderedDict

import os
import tempfile
import stat

from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from .._exceptions import BstError
from .directory import Directory, VirtualDirectoryError
from ._filebaseddirectory import FileBasedDirectory
from ..utils import FileListResult, safe_copy, list_relative_paths
from .._cas.cascache import CASCache


class IndexEntry():
    """ Used in our index of names to objects to store the 'modified' flag
    for directory entries. Because we need both the remote_execution_pb2 object
    and our own Directory object for directory entries, we store both. For files
    and symlinks, only pb_object is used. """
    def __init__(self, pb_object, buildstream_object=None, modified=False):
        self.pb_object = pb_object  # Short for 'protocol buffer object')
        self.buildstream_object = buildstream_object
        self.modified = modified


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

    def __init__(self, context, ref=None, parent=None, common_name="untitled", filename=None):
        self.context = context
        self.cas_directory = os.path.join(context.artifactdir, 'cas')
        self.filename = filename
        self.common_name = common_name
        self.pb2_directory = remote_execution_pb2.Directory()
        self.cas_cache = CASCache(self.cas_directory)
        if ref:
            with open(self.cas_cache.objpath(ref), 'rb') as f:
                self.pb2_directory.ParseFromString(f.read())

        self.ref = ref
        self.index = OrderedDict()
        self.parent = parent
        self._directory_read = False
        self._populate_index()

    def _populate_index(self):
        if self._directory_read:
            return
        for entry in self.pb2_directory.directories:
            buildStreamDirectory = CasBasedDirectory(self.context, ref=entry.digest,
                                                     parent=self, filename=entry.name)
            self.index[entry.name] = IndexEntry(entry, buildstream_object=buildStreamDirectory)
        for entry in self.pb2_directory.files:
            self.index[entry.name] = IndexEntry(entry)
        for entry in self.pb2_directory.symlinks:
            self.index[entry.name] = IndexEntry(entry)
        self._directory_read = True

    def _recalculate_recursing_up(self, caller=None):
        """Recalcuate the hash for this directory and store the results in
        the cache.  If this directory has a parent, tell it to
        recalculate (since changing this directory changes an entry in
        the parent).

        """
        self.ref = self.cas_cache.add_object(buffer=self.pb2_directory.SerializeToString())
        if caller:
            old_dir = self._find_pb2_entry(caller.filename)
            self.cas_cache.add_object(digest=old_dir.digest, buffer=caller.pb2_directory.SerializeToString())
        if self.parent:
            self.parent._recalculate_recursing_up(self)

    def _recalculate_recursing_down(self, parent=None):
        """Recalcuate the hash for this directory and any
        subdirectories. Hashes for subdirectories should be calculated
        and stored after a significant operation (e.g. an
        import_files() call) but not after adding each file, as that
        is extremely wasteful.

        """
        for entry in self.pb2_directory.directories:
            self.index[entry.name].buildstream_object._recalculate_recursing_down(entry)

        if parent:
            self.ref = self.cas_cache.add_object(digest=parent.digest, buffer=self.pb2_directory.SerializeToString())
        else:
            self.ref = self.cas_cache.add_object(buffer=self.pb2_directory.SerializeToString())
        # We don't need to do anything more than that; files were already added ealier, and symlinks are
        # part of the directory structure.

    def _find_pb2_entry(self, name):
        if name in self.index:
            return self.index[name].pb_object
        return None

    def _find_self_in_parent(self):
        assert self.parent is not None
        parent = self.parent
        for (k, v) in parent.index.items():
            if v.buildstream_object == self:
                return k
        return None

    def _add_directory(self, name):
        if name in self.index:
            newdir = self.index[name].buildstream_object
            if not isinstance(newdir, CasBasedDirectory):
                # TODO: This may not be an actual error; it may actually overwrite it
                raise VirtualDirectoryError("New directory {} in {} would overwrite existing non-directory of type {}"
                                            .format(name, str(self), type(newdir)))
            dirnode = self._find_pb2_entry(name)
        else:
            newdir = CasBasedDirectory(self.context, parent=self, filename=name)
            dirnode = self.pb2_directory.directories.add()

        dirnode.name = name

        # Calculate the hash for an empty directory
        new_directory = remote_execution_pb2.Directory()
        self.cas_cache.add_object(digest=dirnode.digest, buffer=new_directory.SerializeToString())
        self.index[name] = IndexEntry(dirnode, buildstream_object=newdir)
        return newdir

    def _add_new_file(self, basename, filename):
        filenode = self.pb2_directory.files.add()
        filenode.name = filename
        self.cas_cache.add_object(digest=filenode.digest, path=os.path.join(basename, filename))
        is_executable = os.access(os.path.join(basename, filename), os.X_OK)
        filenode.is_executable = is_executable
        self.index[filename] = IndexEntry(filenode, modified=(filename in self.index))

    def _add_new_link(self, basename, filename):
        existing_link = self._find_pb2_entry(filename)
        if existing_link:
            symlinknode = existing_link
        else:
            symlinknode = self.pb2_directory.symlinks.add()
        symlinknode.name = filename
        # A symlink node has no digest.
        symlinknode.target = os.readlink(os.path.join(basename, filename))
        self.index[filename] = IndexEntry(symlinknode, modified=(existing_link is not None))

    def delete_entry(self, name):
        for collection in [self.pb2_directory.files, self.pb2_directory.symlinks, self.pb2_directory.directories]:
            if name in collection:
                collection.remove(name)
        if name in self.index:
            del self.index[name]

    def descend(self, subdirectory_spec, create=False):
        """Descend one or more levels of directory hierarchy and return a new
        Directory object for that directory.

        Arguments:
        * subdirectory_spec (list of strings): A list of strings which are all directory
          names.
        * create (boolean): If this is true, the directories will be created if
          they don't already exist.

        Note: At the moment, creating a directory by descending does
        not update this object in the CAS cache. However, performing
        an import_files() into a subdirectory of any depth obtained by
        descending from this object *will* cause this directory to be
        updated and stored.

        """

        # It's very common to send a directory name instead of a list and this causes
        # bizarre errors, so check for it here
        if not isinstance(subdirectory_spec, list):
            subdirectory_spec = [subdirectory_spec]

        # Because of the way split works, it's common to get a list which begins with
        # an empty string. Detect these and remove them.
        while subdirectory_spec and subdirectory_spec[0] == "":
            subdirectory_spec.pop(0)

        # Descending into [] returns the same directory.
        if not subdirectory_spec:
            return self

        if subdirectory_spec[0] in self.index:
            entry = self.index[subdirectory_spec[0]].buildstream_object
            if isinstance(entry, CasBasedDirectory):
                return entry.descend(subdirectory_spec[1:], create)
            else:
                error = "Cannot descend into {}, which is a '{}' in the directory {}"
                raise VirtualDirectoryError(error.format(subdirectory_spec[0],
                                                         type(entry).__name__,
                                                         self))
        else:
            if create:
                newdir = self._add_directory(subdirectory_spec[0])
                return newdir.descend(subdirectory_spec[1:], create)
            else:
                error = "No entry called '{}' found in {}. There are directories called {}."
                directory_list = ",".join([entry.name for entry in self.pb2_directory.directories])
                raise VirtualDirectoryError(error.format(subdirectory_spec[0], str(self),
                                                         directory_list))
        return None

    def find_root(self):
        """ Finds the root of this directory tree by following 'parent' until there is
        no parent. """
        if self.parent:
            return self.parent.find_root()
        else:
            return self

    def _resolve_symlink_or_directory(self, name):
        """Used only by _import_files_from_directory. Tries to resolve a
        directory name or symlink name. 'name' must be an entry in this
        directory. It must be a single symlink or directory name, not a path
        separated by path separators. If it's an existing directory name, it
        just returns the Directory object for that. If it's a symlink, it will
        attempt to find the target of the symlink and return that as a
        Directory object.

        If a symlink target doesn't exist, it will attempt to create it
        as a directory as long as it's within this directory tree.
        """

        if isinstance(self.index[name].buildstream_object, Directory):
            return self.index[name].buildstream_object
        # OK then, it's a symlink
        symlink = self._find_pb2_entry(name)
        absolute = symlink.target.startswith(CasBasedDirectory._pb2_absolute_path_prefix)
        if absolute:
            root = self.find_root()
        else:
            root = self
        directory = root
        components = symlink.target.split(CasBasedDirectory._pb2_path_sep)
        for c in components:
            if c == "..":
                directory = directory.parent
            else:
                directory = directory.descend(c, create=True)
        return directory

    def _check_replacement(self, name, path_prefix, fileListResult):
        """ Checks whether 'name' exists, and if so, whether we can overwrite it.
        If we can, add the name to 'overwritten_files' and delete the existing entry.
        Returns 'True' if the import should go ahead.
        fileListResult.overwritten and fileListResult.ignore are updated depending
        on the result. """
        existing_entry = self._find_pb2_entry(name)
        relative_pathname = os.path.join(path_prefix, name)
        if existing_entry is None:
            return True
        if (isinstance(existing_entry,
                       (remote_execution_pb2.FileNode, remote_execution_pb2.SymlinkNode))):
            fileListResult.overwritten.append(relative_pathname)
            return True
        elif isinstance(existing_entry, remote_execution_pb2.DirectoryNode):
            # If 'name' maps to a DirectoryNode, then there must be an entry in index
            # pointing to another Directory.
            if self.index[name].buildstream_object.is_empty():
                self.delete_entry(name)
                fileListResult.overwritten.append(relative_pathname)
                return True
            else:
                # We can't overwrite a non-empty directory, so we just ignore it.
                fileListResult.ignored.append(relative_pathname)
                return False
        assert False, ("Entry '{}' is not a recognised file/link/directory and not None; it is {}"
                       .format(name, type(existing_entry)))
        return False  # In case asserts are disabled

    def _import_directory_recursively(self, directory_name, source_directory, remaining_path, path_prefix):
        """ _import_directory_recursively and _import_files_from_directory will be called alternately
        as a directory tree is descended. """
        if directory_name in self.index:
            subdir = self._resolve_symlink_or_directory(directory_name)
        else:
            subdir = self._add_directory(directory_name)
        new_path_prefix = os.path.join(path_prefix, directory_name)
        subdir_result = subdir._import_files_from_directory(os.path.join(source_directory, directory_name),
                                                            [os.path.sep.join(remaining_path)],
                                                            path_prefix=new_path_prefix)
        return subdir_result

    def _import_files_from_directory(self, source_directory, files, path_prefix=""):
        """ Imports files from a traditional directory """
        result = FileListResult()
        for entry in sorted(files):
            split_path = entry.split(os.path.sep)
            # The actual file on the FS we're importing
            import_file = os.path.join(source_directory, entry)
            # The destination filename, relative to the root where the import started
            relative_pathname = os.path.join(path_prefix, entry)
            if len(split_path) > 1:
                directory_name = split_path[0]
                # Hand this off to the importer for that subdir. This will only do one file -
                # a better way would be to hand off all the files in this subdir at once.
                subdir_result = self._import_directory_recursively(directory_name, source_directory,
                                                                   split_path[1:], path_prefix)
                result.combine(subdir_result)
            elif os.path.islink(import_file):
                if self._check_replacement(entry, path_prefix, result):
                    self._add_new_link(source_directory, entry)
                    result.files_written.append(relative_pathname)
            elif os.path.isdir(import_file):
                # A plain directory which already exists isn't a problem; just ignore it.
                if entry not in self.index:
                    self._add_directory(entry)
            elif os.path.isfile(import_file):
                if self._check_replacement(entry, path_prefix, result):
                    self._add_new_file(source_directory, entry)
                    result.files_written.append(relative_pathname)
        return result

    def import_files(self, external_pathspec, *, files=None,
                     report_written=True, update_utimes=False,
                     can_link=False):
        """Imports some or all files from external_path into this directory.

        Keyword arguments: external_pathspec: Either a string
        containing a pathname, or a Directory object, to use as the
        source.

        files (list of strings): A list of all the files relative to
        the external_pathspec to copy. If 'None' is supplied, all
        files are copied.

        report_written (bool): Return the full list of files
        written. Defaults to true. If false, only a list of
        overwritten files is returned.

        update_utimes (bool): Currently ignored, since CAS does not store utimes.

        can_link (bool): Ignored, since hard links do not have any meaning within CAS.
        """
        if isinstance(external_pathspec, FileBasedDirectory):
            source_directory = external_pathspec._get_underlying_directory()
        elif isinstance(external_pathspec, CasBasedDirectory):
            # TODO: This transfers from one CAS to another via the
            # filesystem, which is very inefficient. Alter this so it
            # transfers refs across directly.
            with tempfile.TemporaryDirectory(prefix="roundtrip") as tmpdir:
                external_pathspec.export_files(tmpdir)
                if files is None:
                    files = list_relative_paths(tmpdir)
                result = self._import_files_from_directory(tmpdir, files=files)
            return result
        else:
            source_directory = external_pathspec

        if files is None:
            files = list_relative_paths(source_directory)

        # TODO: No notice is taken of report_written, update_utimes or can_link.
        # Current behaviour is to fully populate the report, which is inefficient,
        # but still correct.
        result = self._import_files_from_directory(source_directory, files=files)

        # We need to recalculate and store the hashes of all directories both
        # up and down the tree; we have changed our directory by importing files
        # which changes our hash and all our parents' hashes of us. The trees
        # lower down need to be stored in the CAS as they are not automatically
        # added during construction.
        self._recalculate_recursing_down()
        if self.parent:
            self.parent._recalculate_recursing_up(self)
        return result

    def set_deterministic_mtime(self):
        """ Sets a static modification time for all regular files in this directory.
        Since we don't store any modification time, we don't need to do anything.
        """
        pass

    def set_deterministic_user(self):
        """ Sets all files in this directory to the current user's euid/egid.
        We also don't store user data, so this can be ignored.
        """
        pass

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

        if not os.path.exists(to_directory):
            os.mkdir(to_directory)

        for entry in self.pb2_directory.directories:
            if entry.name not in self.index:
                raise VirtualDirectoryError("CasDir {} contained {} in directories but not in the index"
                                            .format(str(self), entry.name))
            if not self._directory_read:
                raise VirtualDirectoryError("CasDir {} has not been indexed yet".format(str(self)))
            dest_dir = os.path.join(to_directory, entry.name)
            if not os.path.exists(dest_dir):
                os.mkdir(dest_dir)
            target = self.descend([entry.name])
            target.export_files(dest_dir)
        for entry in self.pb2_directory.files:
            # Extract the entry to a single file
            dest_name = os.path.join(to_directory, entry.name)
            src_name = self.cas_cache.objpath(entry.digest)
            safe_copy(src_name, dest_name)
            if entry.is_executable:
                os.chmod(dest_name, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR |
                         stat.S_IRGRP | stat.S_IXGRP |
                         stat.S_IROTH | stat.S_IXOTH)
        for entry in self.pb2_directory.symlinks:
            src_name = os.path.join(to_directory, entry.name)
            target_name = entry.target
            try:
                os.symlink(target_name, src_name)
            except FileExistsError as e:
                raise BstError(("Cannot create a symlink named {} pointing to {}." +
                                " The original error was: {}").
                               format(src_name, entry.target, e))

    def export_to_tar(self, tarfile, destination_dir, mtime=0):
        raise NotImplementedError()

    def mark_changed(self):
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
            if isinstance(i.buildstream_object, CasBasedDirectory):
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

    def list_modified_paths(self):
        """Provide a list of relative paths which have been modified since the
        last call to mark_unmodified.

        Return value: List(str) - list of modified paths
        """

        filelist = []
        for (k, v) in self.index.items():
            if isinstance(v.buildstream_object, CasBasedDirectory):
                filelist.extend([k + os.path.sep + x for x in v.buildstream_object.list_modified_paths()])
            elif isinstance(v.pb_object, remote_execution_pb2.FileNode) and v.modified:
                filelist.append(k)
        return filelist

    def list_relative_paths(self):
        """Provide a list of all relative paths.

        NOTE: This list is not in the same order as utils.list_relative_paths.

        Return value: List(str) - list of all paths
        """

        filelist = []
        for (k, v) in self.index.items():
            if isinstance(v.buildstream_object, CasBasedDirectory):
                filelist.extend([k + os.path.sep + x for x in v.buildstream_object.list_relative_paths()])
            elif isinstance(v.pb_object, remote_execution_pb2.FileNode):
                filelist.append(k)
        return filelist

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
        raise VirtualDirectoryError("_get_underlying_directory was called on a CAS-backed directory," +
                                    " which has no underlying directory.")
