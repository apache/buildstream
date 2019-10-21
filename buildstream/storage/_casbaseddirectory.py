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

from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from .directory import Directory, VirtualDirectoryError, _FileType
from ._filebaseddirectory import FileBasedDirectory
from ..utils import FileListResult, list_relative_paths


class IndexEntry():
    """ Used in our index of names to objects to store the 'modified' flag
    for directory entries. Because we need both the remote_execution_pb2 object
    and our own Directory object for directory entries, we store both. For files
    and symlinks, only pb_object is used. """
    def __init__(self, pb_object, entrytype, buildstream_object=None, modified=False):
        self.pb_object = pb_object  # Short for 'protocol buffer object')
        self.type = entrytype
        self.buildstream_object = buildstream_object
        self.modified = modified

    def get_directory(self, parent):
        if not self.buildstream_object:
            self.buildstream_object = CasBasedDirectory(parent.cas_cache, ref=self.pb_object.digest,
                                                        parent=parent, filename=self.pb_object.name)

        return self.buildstream_object


class ResolutionException(VirtualDirectoryError):
    """ Superclass of all exceptions that can be raised by
    CasBasedDirectory._resolve. Should not be used outside this module. """
    pass


class InfiniteSymlinkException(ResolutionException):
    """ Raised when an infinite symlink loop is found. """
    pass


class AbsoluteSymlinkException(ResolutionException):
    """Raised if we try to follow an absolute symlink (i.e. one whose
    target starts with the path separator) and we have disallowed
    following such symlinks.
    """
    pass


class UnexpectedFileException(ResolutionException):
    """Raised if we were found a file where a directory or symlink was
    expected, for example we try to resolve a symlink pointing to
    /a/b/c but /a/b is a file.
    """
    def __init__(self, message=""):
        """Allow constructor with no arguments, since this can be raised in
        places where there isn't sufficient information to write the
        message.
        """
        super().__init__(message)


class _Resolver():
    """A class for resolving symlinks inside CAS-based directories. As
    well as providing a namespace for some functions, this also
    contains two flags which are constant throughout one resolution
    operation and the 'seen_objects' list used to detect infinite
    symlink loops.

    """

    def __init__(self, absolute_symlinks_resolve=True, force_create=False):
        self.absolute_symlinks_resolve = absolute_symlinks_resolve
        self.force_create = force_create
        self.seen_objects = []

    def resolve(self, name, directory):
        """Resolves any name to an object. If the name points to a symlink in
        the directory, it returns the thing it points to,
        recursively.

        Returns a CasBasedDirectory, FileNode or None. None indicates
        either that 'target' does not exist in this directory, or is a
        symlink chain which points to a nonexistent name (broken
        symlink).

        Raises:

        - InfiniteSymlinkException if 'name' points to an infinite
          symlink loop.
        - AbsoluteSymlinkException if 'name' points to an absolute
          symlink and absolute_symlinks_resolve is False.
        - UnexpectedFileException if at any point during resolution we
          find a file which we expected to be a directory or symlink.

        If force_create is set, this will attempt to create
        directories to make symlinks and directories resolve.  Files
        present in symlink target paths will also be removed and
        replaced with directories.  If force_create is off, this will
        never alter 'directory'.

        """

        # First check for nonexistent things or 'normal' objects and return them
        if name not in directory.index:
            return None
        index_entry = directory.index[name]
        if index_entry.type == _FileType.DIRECTORY:
            return index_entry.get_directory(directory)
        elif index_entry.type == _FileType.REGULAR_FILE:
            return index_entry.pb_object

        # Now we must be dealing with a symlink.
        assert index_entry.type == _FileType.SYMLINK

        symlink_object = index_entry.pb_object
        if symlink_object in self.seen_objects:
            # Infinite symlink loop detected
            message = ("Infinite symlink loop found during resolution. " +
                       "First repeated element is {}".format(name))
            raise InfiniteSymlinkException(message=message)

        self.seen_objects.append(symlink_object)

        components = symlink_object.target.split(CasBasedDirectory._pb2_path_sep)
        absolute = symlink_object.target.startswith(CasBasedDirectory._pb2_absolute_path_prefix)

        if absolute:
            if self.absolute_symlinks_resolve:
                directory = directory.find_root()
                # Discard the first empty element
                components.pop(0)
            else:
                # Unresolvable absolute symlink
                message = "{} is an absolute symlink, which was disallowed during resolution".format(name)
                raise AbsoluteSymlinkException(message=message)

        resolution = directory
        while components and isinstance(resolution, CasBasedDirectory):
            c = components.pop(0)
            directory = resolution

            try:
                resolution = self._resolve_path_component(c, directory, components)
            except UnexpectedFileException as original:
                errormsg = ("Reached a file called {} while trying to resolve a symlink; " +
                            "cannot proceed. The remaining path components are {}.")
                raise UnexpectedFileException(errormsg.format(c, components)) from original

        return resolution

    def _resolve_path_component(self, c, directory, components_remaining):
        if c == ".":
            resolution = directory
        elif c == "..":
            if directory.parent is not None:
                resolution = directory.parent
            else:
                # If directory.parent *is* None, this is an attempt to
                # access '..' from the root, which is valid under
                # POSIX; it just returns the root.
                resolution = directory
        elif c in directory.index:
            try:
                resolution = self._resolve_through_files(c, directory, components_remaining)
            except UnexpectedFileException as original:
                errormsg = ("Reached a file called {} while trying to resolve a symlink; " +
                            "cannot proceed. The remaining path components are {}.")
                raise UnexpectedFileException(errormsg.format(c, components_remaining)) from original
        else:
            # c is not in our index
            if self.force_create:
                resolution = directory.descend(c, create=True)
            else:
                resolution = None
        return resolution

    def _resolve_through_files(self, c, directory, require_traversable):
        """A wrapper to resolve() which deals with files being found
        in the middle of paths, for example trying to resolve a symlink
        which points to /usr/lib64/libfoo when 'lib64' is a file.

        require_traversable: If this is True, never return a file
        node.  Instead, if force_create is set, destroy the file node,
        then create and return a normal directory in its place. If
        force_create is off, throws ResolutionException.

        """
        resolved_thing = self.resolve(c, directory)

        if isinstance(resolved_thing, remote_execution_pb2.FileNode):
            if require_traversable:
                # We have components still to resolve, but one of the path components
                # is a file.
                if self.force_create:
                    directory.delete_entry(c)
                    resolved_thing = directory.descend(c, create=True)
                else:
                    # This is a signal that we hit a file, but don't
                    # have the data to give a proper message, so the
                    # caller should reraise this with a proper
                    # description.
                    raise UnexpectedFileException()

        return resolved_thing


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

    def __init__(self, cas_cache, ref=None, parent=None, common_name="untitled", filename=None):
        self.filename = filename
        self.common_name = common_name
        self.pb2_directory = remote_execution_pb2.Directory()
        self.cas_cache = cas_cache
        if ref:
            with open(self.cas_cache.objpath(ref), 'rb') as f:
                self.pb2_directory.ParseFromString(f.read())

        self.ref = ref
        self.index = {}
        self.parent = parent
        self._directory_read = False
        self._populate_index()

    def _populate_index(self):
        if self._directory_read:
            return
        for entry in self.pb2_directory.directories:
            self.index[entry.name] = IndexEntry(entry, _FileType.DIRECTORY)
        for entry in self.pb2_directory.files:
            self.index[entry.name] = IndexEntry(entry, _FileType.REGULAR_FILE)
        for entry in self.pb2_directory.symlinks:
            self.index[entry.name] = IndexEntry(entry, _FileType.SYMLINK)
        self._directory_read = True

    def _recalculate_recursing_up(self, caller=None):
        """Recalcuate the hash for this directory and store the results in
        the cache.  If this directory has a parent, tell it to
        recalculate (since changing this directory changes an entry in
        the parent).

        """
        if caller:
            old_dir = self._find_pb2_entry(caller.filename)
            self.cas_cache.add_object(digest=old_dir.digest, buffer=caller.pb2_directory.SerializeToString())
        self.ref = self.cas_cache.add_object(buffer=self.pb2_directory.SerializeToString())
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
            subdir = self.index[entry.name].buildstream_object
            if subdir:
                subdir._recalculate_recursing_down(entry)

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
        assert name not in self.index

        newdir = CasBasedDirectory(self.cas_cache, parent=self, filename=name)
        dirnode = self.pb2_directory.directories.add()
        dirnode.name = name

        # Calculate the hash for an empty directory
        new_directory = remote_execution_pb2.Directory()
        self.cas_cache.add_object(digest=dirnode.digest, buffer=new_directory.SerializeToString())
        self.index[name] = IndexEntry(dirnode, _FileType.DIRECTORY, buildstream_object=newdir)
        return newdir

    def _add_file(self, basename, filename, modified=False):
        filenode = self.pb2_directory.files.add()
        filenode.name = filename
        self.cas_cache.add_object(digest=filenode.digest, path=os.path.join(basename, filename))
        is_executable = os.access(os.path.join(basename, filename), os.X_OK)
        filenode.is_executable = is_executable
        self.index[filename] = IndexEntry(filenode, _FileType.REGULAR_FILE,
                                          modified=modified or filename in self.index)

    def _copy_link_from_filesystem(self, basename, filename):
        self._add_new_link_direct(filename, os.readlink(os.path.join(basename, filename)))

    def _add_new_link_direct(self, name, target):
        entry = self.index.get(name)
        if entry:
            symlinknode = entry.pb_object
        else:
            symlinknode = self.pb2_directory.symlinks.add()
        symlinknode.name = name
        # A symlink node has no digest.
        symlinknode.target = target
        self.index[name] = IndexEntry(symlinknode, _FileType.SYMLINK, modified=(entry is not None))

    def delete_entry(self, name):
        for collection in [self.pb2_directory.files, self.pb2_directory.symlinks, self.pb2_directory.directories]:
            for thing in collection:
                if thing.name == name:
                    collection.remove(thing)
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
            entry = self.index[subdirectory_spec[0]]
            if entry.type == _FileType.DIRECTORY:
                subdir = entry.get_directory(self)
                return subdir.descend(subdirectory_spec[1:], create)
            else:
                # May be a symlink
                target = self._resolve(subdirectory_spec[0], force_create=create)
                if isinstance(target, CasBasedDirectory):
                    return target
                error = "Cannot descend into {}, which is a '{}' in the directory {}"
                raise VirtualDirectoryError(error.format(subdirectory_spec[0],
                                                         type(self.index[subdirectory_spec[0]].pb_object).__name__,
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

    def _resolve(self, name, absolute_symlinks_resolve=True, force_create=False):
        resolver = _Resolver(absolute_symlinks_resolve, force_create)
        return resolver.resolve(name, self)

    def _check_replacement(self, name, path_prefix, fileListResult):
        """ Checks whether 'name' exists, and if so, whether we can overwrite it.
        If we can, add the name to 'overwritten_files' and delete the existing entry.
        Returns 'True' if the import should go ahead.
        fileListResult.overwritten and fileListResult.ignore are updated depending
        on the result. """
        existing_entry = self.index.get(name)
        relative_pathname = os.path.join(path_prefix, name)
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

    def _replace_anything_with_dir(self, name, path_prefix, overwritten_files_list):
        self.delete_entry(name)
        subdir = self._add_directory(name)
        overwritten_files_list.append(os.path.join(path_prefix, name))
        return subdir

    def _import_files_from_directory(self, source_directory, files, path_prefix=""):
        """ Imports files from a traditional directory. """

        def _ensure_followable(name, path_prefix):
            """ Makes sure 'name' is a directory or symlink to a directory which can be descended into. """
            if isinstance(self.index[name].buildstream_object, Directory):
                return self.descend(name)
            try:
                target = self._resolve(name, force_create=True)
            except InfiniteSymlinkException:
                return self._replace_anything_with_dir(name, path_prefix, result.overwritten)
            if isinstance(target, CasBasedDirectory):
                return target
            elif isinstance(target, remote_execution_pb2.FileNode):
                return self._replace_anything_with_dir(name, path_prefix, result.overwritten)
            return target

        def _import_directory_recursively(directory_name, source_directory, remaining_path, path_prefix):
            """ _import_directory_recursively and _import_files_from_directory will be called alternately
            as a directory tree is descended. """
            if directory_name in self.index:
                subdir = _ensure_followable(directory_name, path_prefix)
            else:
                subdir = self._add_directory(directory_name)
            new_path_prefix = os.path.join(path_prefix, directory_name)
            subdir_result = subdir._import_files_from_directory(os.path.join(source_directory, directory_name),
                                                                [os.path.sep.join(remaining_path)],
                                                                path_prefix=new_path_prefix)
            return subdir_result

        result = FileListResult()
        for entry in files:
            split_path = entry.split(os.path.sep)
            # The actual file on the FS we're importing
            import_file = os.path.join(source_directory, entry)
            # The destination filename, relative to the root where the import started
            relative_pathname = os.path.join(path_prefix, entry)
            if len(split_path) > 1:
                directory_name = split_path[0]
                # Hand this off to the importer for that subdir.

                # It would be advantageous to batch these together by
                # directory_name. However, we can't do it out of
                # order, since importing symlinks affects the results
                # of other imports.
                subdir_result = _import_directory_recursively(directory_name, source_directory,
                                                              split_path[1:], path_prefix)
                result.combine(subdir_result)
            elif os.path.islink(import_file):
                if self._check_replacement(entry, path_prefix, result):
                    self._copy_link_from_filesystem(source_directory, entry)
                    result.files_written.append(relative_pathname)
            elif os.path.isdir(import_file):
                # A plain directory which already exists isn't a problem; just ignore it.
                if entry not in self.index:
                    self._add_directory(entry)
            elif os.path.isfile(import_file):
                if self._check_replacement(entry, path_prefix, result):
                    self._add_file(source_directory, entry, modified=relative_pathname in result.overwritten)
                    result.files_written.append(relative_pathname)
        return result

    @staticmethod
    def _files_in_subdir(sorted_files, dirname):
        """Filters sorted_files and returns only the ones which have
           'dirname' as a prefix, with that prefix removed.

        """
        if not dirname.endswith(os.path.sep):
            dirname += os.path.sep
        return [f[len(dirname):] for f in sorted_files if f.startswith(dirname)]

    def _partial_import_cas_into_cas(self, source_directory, files, path_prefix="", file_list_required=True):
        """ Import only the files and symlinks listed in 'files' from source_directory to this one.
        Args:
           source_directory (:class:`.CasBasedDirectory`): The directory to import from
           files ([str]): List of pathnames to import. Must be a list, not a generator.
           path_prefix (str): Prefix used to add entries to the file list result.
           file_list_required: Whether to update the file list while processing.
        """
        result = FileListResult()
        processed_directories = set()
        for f in files:
            fullname = os.path.join(path_prefix, f)
            components = f.split(os.path.sep)
            if len(components) > 1:
                # We are importing a thing which is in a subdirectory. We may have already seen this dirname
                # for a previous file.
                dirname = components[0]
                if dirname not in processed_directories:
                    # Now strip off the first directory name and import files recursively.
                    subcomponents = CasBasedDirectory._files_in_subdir(files, dirname)
                    # We will fail at this point if there is a file or symlink to file called 'dirname'.
                    if dirname in self.index:
                        resolved_component = self._resolve(dirname, force_create=True)
                        if isinstance(resolved_component, remote_execution_pb2.FileNode):
                            dest_subdir = self._replace_anything_with_dir(dirname, path_prefix, result.overwritten)
                        else:
                            dest_subdir = resolved_component
                    else:
                        dest_subdir = self.descend(dirname, create=True)
                    src_subdir = source_directory.descend(dirname)
                    import_result = dest_subdir._partial_import_cas_into_cas(src_subdir, subcomponents,
                                                                             path_prefix=fullname,
                                                                             file_list_required=file_list_required)
                    result.combine(import_result)
                processed_directories.add(dirname)
            elif source_directory.index[f].type == _FileType.DIRECTORY:
                # The thing in the input file list is a directory on
                # its own. We don't need to do anything other than create it if it doesn't exist.
                # If we already have an entry with the same name that isn't a directory, that
                # will be dealt with when importing files in this directory.
                if f not in self.index:
                    self.descend(f, create=True)
            else:
                # We're importing a file or symlink - replace anything with the same name.
                importable = self._check_replacement(f, path_prefix, result)
                if importable:
                    entry = source_directory.index[f]
                    item = entry.pb_object
                    if entry.type == _FileType.REGULAR_FILE:
                        filenode = self.pb2_directory.files.add(digest=item.digest, name=f,
                                                                is_executable=item.is_executable)
                        self.index[f] = IndexEntry(filenode, _FileType.REGULAR_FILE, modified=True)
                    else:
                        assert entry.type == _FileType.SYMLINK
                        self._add_new_link_direct(name=f, target=item.target)
                    result.files_written.append(os.path.join(path_prefix, f))
                else:
                    result.ignored.append(os.path.join(path_prefix, f))
        return result

    def import_files(self, external_pathspec, *, files=None,
                     report_written=True, update_mtime=False,
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

        update_mtime (bool): Currently ignored, since CAS does not store mtimes.

        can_link (bool): Ignored, since hard links do not have any meaning within CAS.
        """

        if files is None:
            if isinstance(external_pathspec, str):
                files = list_relative_paths(external_pathspec)
            else:
                assert isinstance(external_pathspec, Directory)
                files = external_pathspec.list_relative_paths()

        if isinstance(external_pathspec, FileBasedDirectory):
            source_directory = external_pathspec._get_underlying_directory()
            result = self._import_files_from_directory(source_directory, files=files)
        elif isinstance(external_pathspec, str):
            source_directory = external_pathspec
            result = self._import_files_from_directory(source_directory, files=files)
        else:
            assert isinstance(external_pathspec, CasBasedDirectory)
            result = self._partial_import_cas_into_cas(external_pathspec, files=list(files))

        # TODO: No notice is taken of report_written, update_mtime or can_link.
        # Current behaviour is to fully populate the report, which is inefficient,
        # but still correct.

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

        self.cas_cache.checkout(to_directory, self._get_digest(), can_link=can_link)

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

    def list_relative_paths(self, relpath=""):
        """Provide a list of all relative paths.

        Return value: List(str) - list of all paths
        """

        symlink_list = filter(lambda i: i[1].type == _FileType.SYMLINK,
                              self.index.items())
        file_list = list(filter(lambda i: i[1].type == _FileType.REGULAR_FILE,
                                self.index.items()))
        directory_list = filter(lambda i: i[1].type == _FileType.DIRECTORY,
                                self.index.items())

        # We need to mimic the behaviour of os.walk, in which symlinks
        # to directories count as directories and symlinks to file or
        # broken symlinks count as files. os.walk doesn't follow
        # symlinks, so we don't recurse.
        for (k, v) in sorted(symlink_list):
            target = self._resolve(k, absolute_symlinks_resolve=True)
            if isinstance(target, CasBasedDirectory):
                yield os.path.join(relpath, k)
            else:
                file_list.append((k, v))

        if file_list == [] and relpath != "":
            yield relpath
        else:
            for (k, v) in sorted(file_list):
                yield os.path.join(relpath, k)

        for (k, v) in sorted(directory_list):
            subdir = v.get_directory(self)
            yield from subdir.list_relative_paths(relpath=os.path.join(relpath, k))

    def get_size(self):
        total = len(self.pb2_directory.SerializeToString())
        for i in self.index.values():
            if i.type == _FileType.DIRECTORY:
                subdir = i.get_directory(self)
                total += subdir.get_size()
            elif i.type == _FileType.REGULAR_FILE:
                src_name = self.cas_cache.objpath(i.pb_object.digest)
                filesize = os.stat(src_name).st_size
                total += filesize
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
        raise VirtualDirectoryError("_get_underlying_directory was called on a CAS-backed directory," +
                                    " which has no underlying directory.")

    # _get_digest():
    #
    # Return the Digest for this directory.
    #
    # Returns:
    #   (Digest): The Digest protobuf object for the Directory protobuf
    #
    def _get_digest(self):
        if not self.ref:
            self.ref = self.cas_cache.add_object(buffer=self.pb2_directory.SerializeToString())
        return self.ref