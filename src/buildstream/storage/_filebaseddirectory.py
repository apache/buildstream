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
import shutil
import stat
from contextlib import contextmanager
from tarfile import TarFile
from typing import Callable, Optional, Union, List, IO, Iterator

from .directory import Directory, DirectoryError, FileType, FileStat
from .. import utils
from ..utils import BST_ARBITRARY_TIMESTAMP
from ..utils import FileListResult

# FileBasedDirectory intentionally doesn't call its superclass constuctor,
# which is meant to be unimplemented.
# pylint: disable=super-init-not-called
class FileBasedDirectory(Directory):
    def __init__(self, external_directory: str, *, parent: Optional["FileBasedDirectory"] = None) -> None:
        self.__external_directory: str = external_directory
        self.__parent: Optional[FileBasedDirectory] = parent

    def __iter__(self) -> Iterator[str]:
        yield from os.listdir(self.__external_directory)

    def __len__(self) -> int:
        entries = list(os.listdir(self.__external_directory))
        return len(entries)

    def __str__(self) -> str:
        # This returns the whole path (since we don't know where the directory started)
        # which exposes the sandbox directory; we will have to assume for the time being
        # that people will not abuse __str__.
        return self.__external_directory

    #############################################################
    #              Implementation of Public API                 #
    #############################################################

    def open_directory(
        self, path: str, *, create: bool = False, follow_symlinks: bool = False
    ) -> "FileBasedDirectory":
        self._validate_path(path)
        paths = path.split("/")
        return self.__open_directory(paths, create=create, follow_symlinks=follow_symlinks)

    def import_single_file(self, external_pathspec: str) -> FileListResult:
        dstpath = os.path.join(self.__external_directory, os.path.basename(external_pathspec))
        result = FileListResult()
        if os.path.exists(dstpath):
            result.ignored.append(dstpath)
        else:
            shutil.copyfile(external_pathspec, dstpath, follow_symlinks=False)
        return result

    # Add a directory entry deterministically to a tar file
    #
    # This function takes extra steps to ensure the output is deterministic.
    # First, it sorts the results of os.listdir() to ensure the ordering of
    # the files in the archive is the same.  Second, it sets a fixed
    # timestamp for each entry. See also https://bugs.python.org/issue24465.
    def export_to_tar(self, tarfile: TarFile, destination_dir: str, mtime: int = BST_ARBITRARY_TIMESTAMP) -> None:
        # We need directories here, including non-empty ones,
        # so list_relative_paths is not used.
        for filename in sorted(os.listdir(self.__external_directory)):
            source_name = os.path.join(self.__external_directory, filename)
            arcname = os.path.join(destination_dir, filename)
            tarinfo = tarfile.gettarinfo(source_name, arcname)
            tarinfo.mtime = mtime
            tarinfo.uid = 0
            tarinfo.gid = 0
            tarinfo.uname = ""
            tarinfo.gname = ""

            if tarinfo.isreg():
                with open(source_name, "rb") as f:
                    tarfile.addfile(tarinfo, f)
            elif tarinfo.isdir():
                tarfile.addfile(tarinfo)
                self.open_directory(filename).export_to_tar(tarfile, arcname, mtime)
            else:
                tarfile.addfile(tarinfo)

    def list_relative_paths(self) -> Iterator[str]:
        yield from utils.list_relative_paths(self.__external_directory)

    def exists(self, path: str, *, follow_symlinks: bool = False) -> bool:
        try:
            self.stat(path, follow_symlinks=follow_symlinks)
            return True
        except DirectoryError:
            return False

    def stat(self, path: str, *, follow_symlinks: bool = False) -> FileStat:
        self._validate_path(path)
        paths = path.split("/")

        subdir = self.__open_directory(paths[:-1], follow_symlinks=follow_symlinks)
        newpath = os.path.join(subdir.__external_directory, paths[-1])

        try:
            st = os.lstat(newpath)
        except OSError as e:
            raise DirectoryError("Error accessing path '{}': {}".format(newpath, e)) from e

        if follow_symlinks and stat.S_ISLNK(st.st_mode):
            linklocation = os.readlink(newpath)
            if os.path.isabs(linklocation):
                # Call stat on the root, remove the leading "/"
                return subdir.__find_root().stat(linklocation[1:], follow_symlinks=True)
            return subdir.stat(linklocation, follow_symlinks=True)
        else:
            return self.__convert_filestat(st)

    @contextmanager
    def open_file(self, path: str, *, mode: str = "r") -> Iterator[IO]:
        self._validate_path(path)
        paths = path.split("/")

        # Use open_directory() to avoid following symlinks (potentially escaping the sandbox)
        subdir = self.__open_directory(paths[:-1])
        newpath = os.path.join(subdir.__external_directory, paths[-1])

        if mode not in ["r", "rb", "w", "wb", "w+", "w+b", "x", "xb", "x+", "x+b"]:
            raise ValueError("Unsupported mode: `{}`".format(mode))

        if "b" in mode:
            encoding = None
        else:
            encoding = "utf-8"

        if "r" in mode:
            with open(newpath, mode=mode, encoding=encoding) as f:
                yield f
        else:
            if "x" in mode:
                # This check is not atomic, however, we're operating with a
                # single thread in a private directory tree.
                if subdir.exists(path[-1]):
                    raise DirectoryError("{} already exists in {}".format(path[-1], str(subdir)))
                mode = "w" + mode[1:]

            with utils.save_file_atomic(newpath, mode=mode, encoding=encoding) as f:
                yield f

    def file_digest(self, path: str) -> str:
        self._validate_path(path)
        paths = path.split("/")

        # Use open_directory() to avoid following symlinks (potentially escaping the sandbox)
        subdir = self.__open_directory(paths[:-1])
        if subdir.exists(paths[-1]) and not subdir.isfile(paths[-1]):
            raise DirectoryError("Unsupported file type for digest")

        newpath = os.path.join(subdir.__external_directory, paths[-1])
        return utils.sha256sum(newpath)

    def readlink(self, path: str) -> str:
        self._validate_path(path)
        paths = path.split("/")

        # Use open_directory() to avoid following symlinks (potentially escaping the sandbox)
        subdir = self.__open_directory(paths[:-1])
        if subdir.exists(paths[-1]) and not subdir.islink(paths[-1]):
            raise DirectoryError("Unsupported file type for readlink")

        newpath = os.path.join(subdir.__external_directory, paths[-1])
        return os.readlink(newpath)

    def remove(self, path: str, *, recursive: bool = False) -> None:
        self._validate_path(path)
        paths = path.split("/")

        # Use open_directory() to avoid following symlinks (potentially escaping the sandbox)
        subdir = self.__open_directory(paths[:-1])
        newpath = os.path.join(subdir.__external_directory, paths[-1])

        if subdir.isdir(paths[-1]):
            if recursive:
                shutil.rmtree(newpath)
            else:
                try:
                    os.rmdir(newpath)
                except OSError as e:
                    raise DirectoryError("Error removing '{}': {}".format(newpath, e))
        else:
            try:
                os.unlink(newpath)
            except OSError as e:
                raise DirectoryError("Error removing '{}': {}".format(newpath, e))

    def rename(self, src: str, dest: str) -> None:

        self._validate_path(src)
        self._validate_path(dest)
        src_paths = src.split("/")
        dest_paths = dest.split("/")

        # Use open_directory() to avoid following symlinks (potentially escaping the sandbox)
        srcdir = self.__open_directory(src_paths[:-1])
        destdir = self.__open_directory(dest_paths[:-1])
        srcpath = os.path.join(srcdir.__external_directory, src_paths[-1])
        destpath = os.path.join(destdir.__external_directory, dest_paths[-1])

        if destdir.exists(dest_paths[-1]):
            destdir.remove(dest_paths[-1])
        try:
            os.rename(srcpath, destpath)
        except OSError as e:
            raise DirectoryError("Error renaming '{}' -> '{}': {}".format(srcpath, destpath, e))

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
    ) -> FileListResult:

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
            #
            # We've got a source directory to copy from
            #
            import_result = utils.copy_files(
                source_directory,
                self.__external_directory,
                filter_callback=filter_callback,
                ignore_missing=False,
                report_written=True,
            )
            if update_mtime:
                for f in import_result.files_written:
                    os.utime(os.path.join(self.__external_directory, f), times=(update_mtime, update_mtime))
        else:
            #
            # We're dealing with an abstract Directory object
            #
            assert isinstance(external_pathspec, Directory)

            def copy_action(src_path, dest_path, mtime, result):
                utils.safe_copy(src_path, dest_path, result=result)
                utils._set_file_mtime(dest_path, mtime)

            import_result = FileListResult()
            self.__import_files_from_directory(
                external_pathspec,
                copy_action,
                filter_callback,
                update_mtime=update_mtime,
                result=import_result,
            )

        return import_result

    def _export_files(self, to_directory: str, *, can_link: bool = False, can_destroy: bool = False) -> None:
        if can_destroy:
            # Try a simple rename of the sandbox root; if that
            # doesnt cut it, then do the regular link files code path
            try:
                os.rename(self.__external_directory, to_directory)
                return
            except OSError:
                # Proceed using normal link/copy
                pass

        os.makedirs(to_directory, exist_ok=True)
        if can_link:
            utils.link_files(self.__external_directory, to_directory)
        else:
            utils.copy_files(self.__external_directory, to_directory)

    def _set_deterministic_user(self) -> None:
        utils._set_deterministic_user(self.__external_directory)

    def _get_underlying_path(self, filename) -> str:
        return os.path.join(self.__external_directory, filename)

    def _get_underlying_directory(self) -> str:
        return self.__external_directory

    def _get_size(self) -> int:
        return utils._get_dir_size(self.__external_directory)

    #############################################################
    #                      Private methods                      #
    #############################################################
    def __open_directory(
        self, paths: List[str], *, create: bool = False, follow_symlinks: bool = False
    ) -> "FileBasedDirectory":
        current_dir = self

        for path in paths:
            # Skip empty path segments
            if not path:
                continue

            if path == ".":
                continue
            if path == "..":
                if current_dir.__parent is not None:
                    current_dir = current_dir.__parent
                # In POSIX /.. == / so just stay at the root dir
                continue

            new_path = os.path.join(current_dir.__external_directory, path)
            try:
                st = os.lstat(new_path)
                if stat.S_ISDIR(st.st_mode):
                    current_dir = FileBasedDirectory(new_path, parent=current_dir)
                elif follow_symlinks and stat.S_ISLNK(st.st_mode):
                    linklocation = os.readlink(new_path)
                    newpaths = linklocation.split(os.path.sep)
                    if os.path.isabs(linklocation):
                        current_dir = current_dir.__find_root().__open_directory(newpaths, follow_symlinks=True)
                    else:
                        current_dir = current_dir.__open_directory(newpaths, follow_symlinks=True)
                else:
                    raise DirectoryError(
                        "Cannot open '{}': '{}' is not a directory".format(path, new_path),
                        reason="not-a-directory",
                    )
            except FileNotFoundError:
                if create:
                    os.mkdir(new_path)
                    current_dir = FileBasedDirectory(new_path, parent=current_dir)
                else:
                    raise DirectoryError("Cannot open '{}': '{}' does not exist".format(path, new_path))

        return current_dir

    # __convert_filestat()
    #
    # Convert an os.stat_result into a FileStat
    #
    def __convert_filestat(self, st: os.stat_result) -> FileStat:

        file_type: int = 0

        if stat.S_ISREG(st.st_mode):
            file_type = FileType.REGULAR_FILE
        elif stat.S_ISDIR(st.st_mode):
            file_type = FileType.DIRECTORY
        elif stat.S_ISLNK(st.st_mode):
            file_type = FileType.SYMLINK

        # If any of the executable bits are set, lets call it executable
        executable = bool(st.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))

        return FileStat(file_type, executable=executable, size=st.st_size, mtime=st.st_mtime)

    # __find_root()
    #
    # Finds the root of this directory tree by following 'parent' until there is
    # no parent.
    #
    def __find_root(self) -> "FileBasedDirectory":
        if self.__parent:
            return self.__parent.__find_root()
        else:
            return self

    # __import_files_from_directory()
    #
    # Import files from a CAS-based directory.
    #
    def __import_files_from_directory(
        self,
        source_directory: Directory,
        actionfunc: Callable[[str, str, float, FileListResult], None],
        filter_callback: Optional[Callable[[str], bool]] = None,
        *,
        path_prefix: str = "",
        update_mtime: Optional[float] = None,
        result: FileListResult
    ) -> None:

        # Iterate over entries in the source directory
        for name in source_directory:

            # The destination filename, relative to the root where the import started
            relative_pathname = os.path.join(path_prefix, name)

            # The full destination path
            dest_path = os.path.join(self.__external_directory, name)

            is_dir = source_directory.isdir(name)

            if is_dir:
                src_subdir = source_directory.open_directory(name)

                try:
                    create_subdir = not os.path.lexists(dest_path)
                    dest_subdir = self.open_directory(name, create=create_subdir)
                except DirectoryError:
                    raise DirectoryError("Destination is not a directory: /{}".format(relative_pathname))

                dest_subdir.__import_files_from_directory(
                    src_subdir,
                    actionfunc,
                    filter_callback,
                    path_prefix=relative_pathname,
                    result=result,
                    update_mtime=update_mtime,
                )

            if filter_callback and not filter_callback(relative_pathname):
                if is_dir and create_subdir and not dest_subdir:
                    # Complete subdirectory has been filtered out, remove it
                    os.rmdir(dest_subdir.__external_directory)

                # Filename filtered out, move to next
                continue

            if not is_dir:
                if os.path.lexists(dest_path):
                    # Collect overlaps
                    if not os.path.isdir(dest_path):
                        result.overwritten.append(relative_pathname)

                    if not utils.safe_remove(dest_path):
                        result.ignored.append(relative_pathname)
                        continue

                if source_directory.isfile(name):
                    src_path = source_directory._get_underlying_path(name)
                    filestat = source_directory.stat(name)

                    # hardlink files on request, they wont have their mtimes
                    # updated if hardlinking is performed
                    mtime = update_mtime
                    if mtime is None:
                        mtime = filestat.mtime

                    actionfunc(src_path, dest_path, mtime, result)

                    if filestat.executable:
                        os.chmod(
                            dest_path,
                            stat.S_IRUSR
                            | stat.S_IWUSR
                            | stat.S_IXUSR
                            | stat.S_IRGRP
                            | stat.S_IXGRP
                            | stat.S_IROTH
                            | stat.S_IXOTH,
                        )
                    result.files_written.append(relative_pathname)

                elif source_directory.islink(name):
                    link_target = source_directory.readlink(name)
                    os.symlink(link_target, dest_path)
                    result.files_written.append(relative_pathname)
