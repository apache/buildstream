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
#        Jim MacArthur <jim.macarthur@codethink.co.uk>
#        Tristan van Berkom <tristan.vanberkom@codethink.co.uk>

import os
import stat
import tarfile as tarfilelib
from tarfile import TarFile
from contextlib import contextmanager
from io import StringIO, BytesIO
from typing import Callable, Optional, Union, List, IO, Iterator, Dict

from google.protobuf import timestamp_pb2

from .. import utils
from .._cas import CASCache
from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from .directory import Directory, DirectoryError, FileType, FileStat
from ..utils import FileListResult, BST_ARBITRARY_TIMESTAMP


# _IndexEntry()
#
# An object to represent a file, used to track members of a CasBasedDirectory
#
class _IndexEntry:
    def __init__(
        self,
        cas_cache: CASCache,
        name: str,
        entrytype: int,
        *,
        digest=None,
        target: Optional[str] = None,
        is_executable: bool = False,
        directory: Optional["CasBasedDirectory"] = None,
        mtime: Optional[timestamp_pb2.Timestamp] = None  # pylint: disable=no-member
    ) -> None:
        # The CAS cache
        self.cas_cache: CASCache = cas_cache

        # The name of the entry (filename)
        self.name: str = name

        # The type of file (FileType)
        self.type: int = entrytype

        # The digest of the entry, as calculated by CAS
        #
        # This protobuf generated type (remote_execution_pb2.Digest) cannot be annotated
        self.digest = digest

        # The target of a symbolic link (for FileType.SYMLINK)
        self.target: Optional[str] = target

        # Whether the file is executable (for FileType.REGULAR_FILE)
        self.is_executable: bool = is_executable

        # The associated directory object (for FileType.DIRECTORY)
        self.directory: Optional["CasBasedDirectory"] = directory

        # The mtime of the file, if provided
        self.mtime: Optional[timestamp_pb2.Timestamp] = mtime  # pylint: disable=no-member

    def get_directory(self, parent: "CasBasedDirectory") -> "CasBasedDirectory":
        if self.directory is None:
            assert self.type == FileType.DIRECTORY
            self.directory = CasBasedDirectory(self.cas_cache, digest=self.digest, parent=parent, filename=self.name)
            self.digest = None
        return self.directory

    # Get the remote_execution_pb2.Digest for this _IndexEntry
    #
    def get_digest(self):
        if self.directory is not None:
            # directory with buildstream object
            return self.directory._get_digest()
        else:
            # regular file, symlink or directory without buildstream object
            return self.digest

    # clone():
    #
    # Create a deep copy of this object. If this is a directory, a
    # CasBasedDirectory can also be passed to assign an appropriate
    # parent directory.
    #
    def clone(self) -> "_IndexEntry":
        return _IndexEntry(
            self.cas_cache,
            self.name,
            self.type,
            # If this is a directory, the digest will be converted
            # later if necessary. For other non-file types, digests
            # are always None.
            digest=self.get_digest(),
            target=self.target,
            is_executable=self.is_executable,
            mtime=self.mtime,
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _IndexEntry):
            return NotImplemented

        def get_equivalency_properties(e: _IndexEntry):
            return (e.name, e.type, e.target, e.is_executable, e.mtime, e.get_digest())

        return get_equivalency_properties(self) == get_equivalency_properties(other)


# CasBasedDirectory intentionally doesn't call its superclass constuctor,
# which is meant to be unimplemented.
# pylint: disable=super-init-not-called
class CasBasedDirectory(Directory):
    def __init__(
        self,
        cas_cache: CASCache,
        *,
        digest=None,
        parent: Optional["CasBasedDirectory"] = None,
        filename: Optional[str] = None
    ) -> None:
        # The CAS cache
        self.__cas_cache: CASCache = cas_cache

        # The name of this directory
        self.__filename: Optional[str] = filename

        # The remote_execution_pb2.Digest of this directory
        self.__digest = digest

        # The parent directory
        self.__parent: Optional["CasBasedDirectory"] = parent

        # An index of directory entries
        self.__index: Dict[str, _IndexEntry] = {}

        # Whether this directory and it's subdirectories should be read-only
        self.__subtree_read_only: Optional[bool] = None

        if digest:
            self.__populate_index(digest)

    def __iter__(self) -> Iterator[str]:
        yield from self.__index.keys()

    def __len__(self) -> int:
        return len(self.__index)

    def __str__(self) -> str:
        return "[CAS:{}]".format(self.__get_identifier())

    #############################################################
    #              Implementation of Public API                 #
    #############################################################

    def open_directory(self, path: str, *, create: bool = False, follow_symlinks: bool = False) -> "CasBasedDirectory":
        self._validate_path(path)
        paths = path.split("/")
        return self.__open_directory(paths, create=create, follow_symlinks=follow_symlinks)

    def import_single_file(self, external_pathspec: str) -> FileListResult:
        result = FileListResult()
        if self.__check_replacement(os.path.basename(external_pathspec), os.path.dirname(external_pathspec), result):
            self.__add_file(
                os.path.basename(external_pathspec),
                external_pathspec,
                properties=None,
            )
            result.files_written.append(external_pathspec)
        return result

    def export_to_tar(self, tarfile: TarFile, destination_dir: str, mtime: int = BST_ARBITRARY_TIMESTAMP) -> None:
        for filename, entry in sorted(self.__index.items()):
            arcname = os.path.join(destination_dir, filename)
            if entry.type == FileType.DIRECTORY:
                tarinfo = tarfilelib.TarInfo(arcname)
                tarinfo.mtime = mtime
                tarinfo.type = tarfilelib.DIRTYPE
                tarinfo.mode = 0o755
                tarfile.addfile(tarinfo)
                self.open_directory(filename).export_to_tar(tarfile, arcname, mtime)
            elif entry.type == FileType.REGULAR_FILE:
                source_name = self.__cas_cache.objpath(entry.digest)
                tarinfo = tarfilelib.TarInfo(arcname)
                tarinfo.mtime = mtime
                if entry.is_executable:
                    tarinfo.mode |= stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                tarinfo.size = os.path.getsize(source_name)
                with open(source_name, "rb") as f:
                    tarfile.addfile(tarinfo, f)
            elif entry.type == FileType.SYMLINK:
                assert entry.target is not None
                tarinfo = tarfilelib.TarInfo(arcname)
                tarinfo.mtime = mtime
                tarinfo.mode = 0o777
                tarinfo.linkname = entry.target
                tarinfo.type = tarfilelib.SYMTYPE
                sio = StringIO(entry.target)
                bio = BytesIO(sio.read().encode("utf8"))
                tarfile.addfile(tarinfo, bio)
            else:
                raise DirectoryError("can not export file type {} to tar".format(entry.type))

    def list_relative_paths(self) -> Iterator[str]:
        yield from self.__list_prefixed_relative_paths()

    def exists(self, path: str, *, follow_symlinks: bool = False) -> bool:
        self._validate_path(path)
        paths = path.split("/")
        try:
            self.__entry_from_path(paths, follow_symlinks=follow_symlinks)
            return True
        except DirectoryError:
            return False

    def stat(self, path: str, *, follow_symlinks: bool = False) -> FileStat:
        self._validate_path(path)
        paths = path.split("/")
        entry = self.__entry_from_path(paths, follow_symlinks=follow_symlinks)

        if entry.type == FileType.REGULAR_FILE:
            size = entry.get_digest().size_bytes
        elif entry.type == FileType.DIRECTORY:
            size = 0
        elif entry.type == FileType.SYMLINK:
            assert entry.target is not None
            size = len(entry.target)
        else:
            raise DirectoryError("Unsupported file type {}".format(entry.type))

        executable = False
        if entry.type == FileType.DIRECTORY or entry.is_executable:
            executable = True

        mtime: float = BST_ARBITRARY_TIMESTAMP
        if entry.mtime is not None:
            mtime = utils._parse_protobuf_timestamp(entry.mtime)

        return FileStat(entry.type, executable=executable, size=size, mtime=mtime)

    @contextmanager
    def open_file(self, path: str, *, mode: str = "r") -> Iterator[IO]:
        self._validate_path(path)
        paths = path.split("/")

        subdir = self.__open_directory(paths[:-1])
        entry = subdir.__index.get(paths[-1])

        if entry and entry.type != FileType.REGULAR_FILE:
            raise DirectoryError("{} in {} is not a file".format(paths[-1], str(subdir)))

        if mode not in ["r", "rb", "w", "wb", "w+", "w+b", "x", "xb", "x+", "x+b"]:
            raise ValueError("Unsupported mode: `{}`".format(mode))

        if "b" in mode:
            encoding = None
        else:
            encoding = "utf-8"

        if "r" in mode:
            if not entry:
                raise DirectoryError("{} not found in {}".format(paths[-1], str(subdir)))

            # Read-only access, allow direct access to CAS object
            with open(self.__cas_cache.objpath(entry.digest), mode, encoding=encoding) as f:
                yield f
        else:
            if "x" in mode and entry:
                raise DirectoryError("{} already exists in {}".format(paths[-1], str(subdir)))

            with utils._tempnamedfile(mode, encoding=encoding, dir=self.__cas_cache.tmpdir) as f:
                # Make sure the temporary file is readable by buildbox-casd
                os.chmod(f.name, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                yield f
                # Import written temporary file into CAS
                f.flush()
                subdir.__add_file(paths[-1], f.name)

    def file_digest(self, path: str) -> str:
        self._validate_path(path)
        paths = path.split("/")
        entry = self.__entry_from_path(paths)
        if entry.type != FileType.REGULAR_FILE:
            raise DirectoryError("Unsupported file type for digest: {}".format(entry.type))

        return entry.digest.hash

    def readlink(self, path: str) -> str:
        self._validate_path(path)
        paths = path.split("/")
        entry = self.__entry_from_path(paths)
        if entry.type != FileType.SYMLINK:
            raise DirectoryError("Unsupported file type for readlink: {}".format(entry.type))
        assert entry.target is not None
        return entry.target

    def remove(self, path: str, *, recursive: bool = False) -> None:
        self._validate_path(path)
        paths = path.split("/")

        if len(paths) > 1:
            # Delegate remove to subdirectory
            subdir = self.__open_directory(paths[:-1])
            subdir.remove(paths[-1], recursive=recursive)
            return

        name = paths[0]
        entry = self.__index.get(name)
        if not entry:
            raise DirectoryError("{} not found in {}".format(name, str(self)))

        if entry.type == FileType.DIRECTORY and not recursive:
            subdir = entry.get_directory(self)
            if subdir:
                raise DirectoryError("{} is not empty".format(str(subdir)))

        del self.__index[name]
        self.__invalidate_digest()

    def rename(self, src: str, dest: str) -> None:
        self._validate_path(src)
        self._validate_path(dest)
        src_paths = src.split("/")
        dest_paths = dest.split("/")

        srcdir = self.__open_directory(src_paths[:-1])
        entry = srcdir.__entry_from_path([src_paths[-1]])

        destdir = self.__open_directory(dest_paths[:-1])

        srcdir.remove(src_paths[-1], recursive=True)
        entry.name = dest_paths[-1]
        destdir.__add_entry(entry)

    #############################################################
    #             Implementation of Internal API                #
    #############################################################
    def _import_files(
        self,
        external_pathspec: Union[Directory, str],
        *,
        filter_callback: Optional[Callable[[str], bool]] = None,
        update_mtime: Optional[float] = None,
        properties: Optional[List[str]] = None,
        collect_result: bool = True
    ) -> Optional[FileListResult]:
        result = FileListResult() if collect_result else None

        # See if we can get a source directory to copy from
        source_directory: Optional[str] = None
        if isinstance(external_pathspec, str):
            source_directory = external_pathspec
        elif isinstance(external_pathspec, Directory):
            try:
                source_directory = external_pathspec._get_underlying_directory()
            except DirectoryError:
                pass

        if source_directory:
            # Import files from local filesystem by first importing complete
            # directory into CAS (using buildbox-casd) and then importing its
            # content into this CasBasedDirectory using CAS-to-CAS import
            # to write the report, handle possible conflicts (if the target
            # directory is not empty) and apply the optional filter.
            digest = self.__cas_cache.import_directory(source_directory, properties=properties)
            external_pathspec = CasBasedDirectory(self.__cas_cache, digest=digest)

        assert isinstance(external_pathspec, CasBasedDirectory)
        self.__partial_import_cas_into_cas(external_pathspec, filter_callback, result=result)

        return result

    def _export_files(self, to_directory: str, *, can_link: bool = False, can_destroy: bool = False) -> None:
        #
        # This is documented to raise DirectoryError, if we are raising a system error
        # or an error from CAS, it is a bug and we should catch/re-raise from here.
        #
        self.__cas_cache.checkout(to_directory, self._get_digest(), can_link=can_link)

    # We don't store UID/GID in CAS presently, so this can be ignored.
    def _set_deterministic_user(self) -> None:
        pass

    def _get_underlying_path(self, filename) -> str:
        try:
            entry = self.__index[filename]
        except IndexError as e:
            raise DirectoryError("Directory does not contain any filename: {}".format(filename)) from e
        return self.__cas_cache.objpath(entry.digest)

    def _get_underlying_directory(self) -> str:
        # There is no underlying directory for a CAS-backed directory, just raise an error.
        raise DirectoryError(
            "_get_underlying_directory was called on a CAS-backed directory, which has no underlying directory."
        )

    def _get_size(self) -> int:
        digest = self._get_digest()
        total = digest.size_bytes
        for i in self.__index.values():
            if i.type == FileType.DIRECTORY:
                subdir = i.get_directory(self)
                total += subdir._get_size()
            elif i.type == FileType.REGULAR_FILE:
                total += i.digest.size_bytes
            # Symlink nodes are encoded as part of the directory serialization.
        return total

    #############################################################
    #        Internal API (specific to CasBasedDirectory)       #
    #############################################################

    # _clear():
    #
    # Remove all entries from this directory.
    #
    def _clear(self) -> None:
        self.__invalidate_digest()
        self.__index = {}

    # _reset():
    #
    # Replace the contents of this directory with the entries from the specified
    # directory digest.
    #
    # Args:
    #     digest (remote_execution_pb2.Digest): The digest of the replacement directory
    #
    def _reset(self, *, digest=None) -> None:
        self._clear()

        if digest:
            self.__digest = digest
            self.__populate_index(digest)

    # _set_subtree_read_only()
    #
    # Sets this directory as read only
    #
    def _set_subtree_read_only(self, read_only: bool) -> None:
        self.__subtree_read_only = read_only
        self.__invalidate_digest()

    # _apply_changes():
    #
    # Apply changes from dir_a to dir_b to this directory. The use
    # case for this is to merge changes between different workspace
    # versions into a buildtree.
    #
    # If a change was made both to this directory, as well as between
    # the given directories, it is applied, overwriting any changes to
    # this directory. This is desirable because we want to keep user
    # changes, however it may need to be re-considered for other use
    # cases.
    #
    # We perform this computation this way, instead of with a _diff
    # method and a subsequent _apply_diff, because it prevents leaking
    # _IndexEntry objects, which contain mutable references and may
    # therefore cause problems if used outside of this class.
    #
    # Args:
    #     dir_a: The directory from which to start computing differences.
    #     dir_b: The directory whose changes to apply
    #
    def _apply_changes(self, dir_a: "CasBasedDirectory", dir_b: "CasBasedDirectory") -> None:
        # If the digests are the same, the directories are the same
        # (child properties affect the digest). We can skip any work
        # in such a case.
        if dir_a._get_digest() == dir_b._get_digest():
            return

        def get_subdir(entry: _IndexEntry, directory: CasBasedDirectory) -> CasBasedDirectory:
            return directory.__index[entry.name].get_directory(directory)

        def is_dir_in(entry: _IndexEntry, directory: CasBasedDirectory) -> bool:
            return directory.__index[entry.name].type == FileType.DIRECTORY

        # We first check which files were added, and add them to our
        # directory.
        for entry in dir_b.__index.values():
            if self.__contains_entry(entry):
                # We can short-circuit checking entries from b that
                # already exist in our index.
                continue

            if not dir_a.__contains_entry(entry):
                if entry.name in self.__index and is_dir_in(entry, self) and is_dir_in(entry, dir_b):
                    # If the entry changed, and is a directory in both
                    # the current and to-merge-into tree, we need to
                    # merge recursively.

                    # If the entry is not a directory in dir_a, we
                    # want to overwrite the file, but we need an empty
                    # directory for recursion.
                    if entry.name in dir_a.__index and is_dir_in(entry, dir_a):
                        sub_a = get_subdir(entry, dir_a)
                    else:
                        sub_a = CasBasedDirectory(dir_a.__cas_cache)

                    subdir = get_subdir(entry, self)
                    subdir._apply_changes(sub_a, get_subdir(entry, dir_b))
                else:
                    # In any other case, we just add/overwrite the file/directory
                    self.__add_entry(entry)

        # We can't iterate and remove entries at the same time
        to_remove = [entry for entry in dir_a.__index.values() if entry.name not in dir_b.__index]
        for entry in to_remove:
            self.remove(entry.name, recursive=True)

        self.__invalidate_digest()

    #############################################################
    #                      Private methods                      #
    #############################################################

    # _get_digest():
    #
    # Return the Digest for this directory.
    #
    # Returns:
    #   (Digest): The Digest protobuf object for the Directory protobuf
    #
    # Note that this has a single underscore because it is accessed
    # by the private _IndexEntry class
    #
    def _get_digest(self):
        if not self.__digest:
            # Create updated Directory proto
            pb2_directory = remote_execution_pb2.Directory()

            if self.__subtree_read_only is not None:
                node_property = pb2_directory.node_properties.properties.add()
                node_property.name = "SubtreeReadOnly"
                node_property.value = "true" if self.__subtree_read_only else "false"

            for name, entry in sorted(self.__index.items()):
                if entry.type == FileType.DIRECTORY:
                    dirnode = pb2_directory.directories.add()
                    dirnode.name = name

                    # Update digests for subdirectories in DirectoryNodes.
                    # No need to call entry.get_directory().
                    # If it hasn't been instantiated, digest must be up-to-date.
                    subdir = entry.directory
                    if subdir is not None:
                        dirnode.digest.CopyFrom(subdir._get_digest())
                    else:
                        dirnode.digest.CopyFrom(entry.digest)
                elif entry.type == FileType.REGULAR_FILE:
                    filenode = pb2_directory.files.add()
                    filenode.name = name
                    filenode.digest.CopyFrom(entry.digest)
                    filenode.is_executable = entry.is_executable
                    if entry.mtime is not None:
                        filenode.node_properties.mtime.CopyFrom(entry.mtime)
                elif entry.type == FileType.SYMLINK:
                    symlinknode = pb2_directory.symlinks.add()
                    symlinknode.name = name
                    symlinknode.target = entry.target

            self.__digest = self.__cas_cache.add_object(buffer=pb2_directory.SerializeToString())

        return self.__digest

    # __open_directory()
    #
    # Open a directory using a list of already separated path components
    #
    def __open_directory(
        self, paths: List[str], *, create: bool = False, follow_symlinks: bool = False
    ) -> "CasBasedDirectory":
        # Note: At the moment, creating a directory by opening a directory does
        # not update this object in the CAS cache. However, performing
        # an import_files() into a subdirectory of any depth obtained
        # from this object *will* cause this directory to be updated and stored.
        current_dir = self

        for element in paths:
            # Skip empty path segments
            if not element:
                continue

            entry = current_dir.__index.get(element)

            if entry:
                if entry.type == FileType.DIRECTORY:
                    current_dir = entry.get_directory(current_dir)
                elif follow_symlinks and entry.type == FileType.SYMLINK:
                    assert entry.target is not None
                    linklocation = entry.target
                    newpaths = linklocation.split(os.path.sep)
                    if os.path.isabs(linklocation):
                        current_dir = current_dir.__find_root().__open_directory(newpaths, follow_symlinks=True)
                    else:
                        current_dir = current_dir.__open_directory(newpaths, follow_symlinks=True)
                else:
                    error = "Cannot open {}, which is a '{}' in the directory {}"
                    raise DirectoryError(
                        error.format(element, current_dir.__index[element].type, current_dir), reason="not-a-directory"
                    )
            else:
                if element == ".":
                    continue
                if element == "..":
                    if current_dir.__parent is not None:
                        current_dir = current_dir.__parent
                    # In POSIX /.. == / so just stay at the root dir
                    continue
                if create:
                    current_dir = current_dir.__add_directory(element)
                else:
                    error = "'{}' not found in {}"
                    raise DirectoryError(error.format(element, str(current_dir)), reason="directory-not-found")

        return current_dir

    # __populate_index()
    #
    # Populate the _IndexEntry for this digest
    #
    # Args:
    #    digest: A remote_execution_pb2.Digest
    #
    def __populate_index(self, digest) -> None:
        try:
            pb2_directory = remote_execution_pb2.Directory()
            with open(self.__cas_cache.objpath(digest), "rb") as f:
                pb2_directory.ParseFromString(f.read())
        except FileNotFoundError as e:
            raise DirectoryError("Directory not found in local cache: {}".format(e)) from e

        for prop in pb2_directory.node_properties.properties:
            if prop.name == "SubtreeReadOnly":
                self.__subtree_read_only = prop.value == "true"

        for entry in pb2_directory.directories:
            self.__index[entry.name] = _IndexEntry(
                self.__cas_cache, entry.name, FileType.DIRECTORY, digest=entry.digest
            )
        for entry in pb2_directory.files:
            if entry.node_properties.HasField("mtime"):
                mtime = entry.node_properties.mtime
            else:
                mtime = None

            self.__index[entry.name] = _IndexEntry(
                self.__cas_cache,
                entry.name,
                FileType.REGULAR_FILE,
                digest=entry.digest,
                is_executable=entry.is_executable,
                mtime=mtime,
            )
        for entry in pb2_directory.symlinks:
            self.__index[entry.name] = _IndexEntry(self.__cas_cache, entry.name, FileType.SYMLINK, target=entry.target)

    def __add_directory(self, name: str) -> "CasBasedDirectory":
        assert name not in self.__index

        newdir = CasBasedDirectory(self.__cas_cache, parent=self, filename=name)

        self.__index[name] = _IndexEntry(self.__cas_cache, name, FileType.DIRECTORY, directory=newdir)

        self.__invalidate_digest()

        return newdir

    def __add_file(self, name: str, path: str, properties: Optional[List[str]] = None) -> None:
        digest = self.__cas_cache.add_object(path=path)
        is_executable = os.access(path, os.X_OK)
        mtime = None
        if properties and "mtime" in properties:
            mtime = timestamp_pb2.Timestamp()  # pylint: disable=no-member
            utils._get_file_protobuf_mtimestamp(mtime, path)

        entry = _IndexEntry(
            self.__cas_cache,
            name,
            FileType.REGULAR_FILE,
            digest=digest,
            is_executable=is_executable,
            mtime=mtime,
        )
        self.__index[name] = entry

        self.__invalidate_digest()

    def __add_entry(self, entry: _IndexEntry) -> None:
        self.__index[entry.name] = entry.clone()
        self.__invalidate_digest()

    def __contains_entry(self, entry: _IndexEntry) -> bool:
        return entry == self.__index.get(entry.name)

    def __add_new_link_direct(self, name, target) -> None:
        self.__index[name] = _IndexEntry(self.__cas_cache, name, FileType.SYMLINK, target=target)
        self.__invalidate_digest()

    # __check_replacement()
    #
    # Checks whether 'name' exists, and if so, whether we can overwrite it.
    # If we can, add the name to 'overwritten_files' and delete the existing entry.
    # Returns 'True' if the import should go ahead.
    # fileListResult.overwritten and fileListResult.ignore are updated depending
    # on the result.
    #
    def __check_replacement(self, name: str, relative_pathname: str, fileListResult: Optional[FileListResult]) -> bool:
        existing_entry = self.__index.get(name)
        if existing_entry is None:
            return True
        elif existing_entry.type == FileType.DIRECTORY:
            # If 'name' maps to a DirectoryNode, then there must be an entry in index
            # pointing to another Directory.
            subdir = existing_entry.get_directory(self)
            if not subdir:
                self.remove(name)
                if fileListResult is not None:
                    fileListResult.overwritten.append(relative_pathname)
                return True
            else:
                # We can't overwrite a non-empty directory, so we just ignore it.
                if fileListResult is not None:
                    fileListResult.ignored.append(relative_pathname)
                return False
        else:
            self.remove(name)
            if fileListResult is not None:
                fileListResult.overwritten.append(relative_pathname)
            return True

    # __partial_import_cas_into_cas()
    #
    # Import files from a CAS-based directory.
    #
    def __partial_import_cas_into_cas(
        self,
        source_directory: "CasBasedDirectory",
        filter_callback: Optional[Callable[[str], bool]] = None,
        *,
        path_prefix: str = "",
        origin: "CasBasedDirectory" = None,
        result: Optional[FileListResult]
    ) -> None:
        if origin is None:
            origin = self

        for name, entry in source_directory.__index.items():
            # The destination filename, relative to the root where the import started
            relative_pathname = os.path.join(path_prefix, name)

            is_dir = entry.type == FileType.DIRECTORY

            if is_dir:
                create_subdir = name not in self.__index

                if create_subdir and not filter_callback:
                    # If subdirectory does not exist yet and there is no filter,
                    # we can import the whole source directory by digest instead
                    # of importing each directory entry individually.
                    subdir_digest = entry.get_digest()
                    dest_entry = _IndexEntry(self.__cas_cache, name, FileType.DIRECTORY, digest=subdir_digest)
                    self.__index[name] = dest_entry
                    self.__invalidate_digest()

                    # However, we still need to iterate over the directory entries
                    # to fill in `result.files_written`.

                    # Use source subdirectory object if it already exists,
                    # otherwise create object for destination subdirectory.
                    # This is based on the assumption that the destination
                    # subdirectory is more likely to be modified later on
                    # (e.g., by further import_files() calls).
                    if entry.directory is not None:
                        subdir = entry.directory
                    else:
                        subdir = dest_entry.get_directory(self)

                    if result is not None:
                        subdir.__add_files_to_result(path_prefix=relative_pathname, result=result)
                else:
                    src_subdir = source_directory.open_directory(name)
                    if src_subdir == origin:
                        continue

                    try:
                        dest_subdir = self.open_directory(name, create=create_subdir)
                    except DirectoryError:
                        filetype = self.__index[name].type
                        raise DirectoryError(
                            "Destination is a {}, not a directory: /{}".format(filetype, relative_pathname)
                        )

                    dest_subdir.__partial_import_cas_into_cas(
                        src_subdir, filter_callback, path_prefix=relative_pathname, origin=origin, result=result
                    )

            if filter_callback and not filter_callback(relative_pathname):
                if is_dir and create_subdir and not dest_subdir:
                    # Complete subdirectory has been filtered out, remove it
                    self.remove(name)

                # Entry filtered out, move to next
                continue

            if not is_dir:
                if self.__check_replacement(name, relative_pathname, result):
                    if entry.type == FileType.REGULAR_FILE:
                        self.__add_entry(entry)
                    else:
                        assert entry.type == FileType.SYMLINK
                        self.__add_new_link_direct(name=name, target=entry.target)
                    if result is not None:
                        result.files_written.append(relative_pathname)

    # __list_prefixed_relative_paths()
    #
    # Provide a list of all relative paths.
    #
    # Args:
    #    prefix: an optional prefix to the relative paths, this is
    #    also emitted by itself.
    #
    # Yields:
    #    ist of all files with relative paths.
    #
    def __list_prefixed_relative_paths(self, prefix: str = "") -> Iterator[str]:
        file_list = list(filter(lambda i: i[1].type != FileType.DIRECTORY, self.__index.items()))
        directory_list = filter(lambda i: i[1].type == FileType.DIRECTORY, self.__index.items())

        if prefix != "":
            yield prefix

        for (k, v) in sorted(file_list):
            yield os.path.join(prefix, k)

        for (k, v) in sorted(directory_list):
            subdir = v.get_directory(self)
            yield from subdir.__list_prefixed_relative_paths(prefix=os.path.join(prefix, k))

    def __get_identifier(self) -> str:
        path = ""
        if self.__parent:
            path = self.__parent.__get_identifier()
        if self.__filename:
            path += "/" + self.__filename
        else:
            path += "/"
        return path

    def __find_root(self) -> "CasBasedDirectory":
        if self.__parent:
            return self.__parent.__find_root()
        else:
            return self

    def __entry_from_path(self, path: List[str], *, follow_symlinks: bool = False) -> _IndexEntry:
        subdir = self.__open_directory(path[:-1], follow_symlinks=follow_symlinks)
        target = subdir.__index.get(path[-1])
        if target is None:
            raise DirectoryError("{} not found in {}".format(path[-1], str(subdir)))

        if follow_symlinks and target.type == FileType.SYMLINK:
            assert target.target is not None
            linklocation = target.target
            newpath = linklocation.split("/")
            if os.path.isabs(linklocation):
                return subdir.__find_root().__entry_from_path(newpath, follow_symlinks=True)
            return subdir.__entry_from_path(newpath, follow_symlinks=True)
        else:
            return target

    def __invalidate_digest(self) -> None:
        if self.__digest:
            self.__digest = None
            if self.__parent:
                self.__parent.__invalidate_digest()

    def __add_files_to_result(self, *, path_prefix: str, result: FileListResult) -> None:
        for name, entry in self.__index.items():
            # The destination filename, relative to the root where the import started
            relative_pathname = os.path.join(path_prefix, name)

            if entry.type == FileType.DIRECTORY:
                subdir = self.open_directory(name)
                subdir.__add_files_to_result(path_prefix=relative_pathname, result=result)
            else:
                result.files_written.append(relative_pathname)
