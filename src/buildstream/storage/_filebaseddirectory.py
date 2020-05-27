#!/usr/bin/env python3
#
#  Copyright (C) 2018 Bloomberg Finance LP
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
FileBasedDirectory
=========

Implementation of the Directory class which backs onto a normal POSIX filing system.

See also: :ref:`sandboxing`.
"""

import os
import shutil
import stat

from .directory import Directory, VirtualDirectoryError, _FileType
from .. import utils
from ..utils import link_files, copy_files, list_relative_paths, _get_link_mtime, BST_ARBITRARY_TIMESTAMP
from ..utils import _set_deterministic_user, _set_deterministic_mtime
from ..utils import FileListResult

# FileBasedDirectory intentionally doesn't call its superclass constuctor,
# which is meant to be unimplemented.
# pylint: disable=super-init-not-called


class FileBasedDirectory(Directory):
    def __init__(self, external_directory=None, *, parent=None):
        self.external_directory = external_directory
        self.parent = parent

    def descend(self, *paths, create=False, follow_symlinks=False):
        """ See superclass Directory for arguments """

        current_dir = self

        for path in paths:
            # Skip empty path segments
            if not path:
                continue

            if path == ".":
                continue
            if path == "..":
                if current_dir.parent is not None:
                    current_dir = current_dir.parent
                # In POSIX /.. == / so just stay at the root dir
                continue

            new_path = os.path.join(current_dir.external_directory, path)
            try:
                st = os.lstat(new_path)
                if stat.S_ISDIR(st.st_mode):
                    current_dir = FileBasedDirectory(new_path, parent=current_dir)
                elif follow_symlinks and stat.S_ISLNK(st.st_mode):
                    linklocation = os.readlink(new_path)
                    newpaths = linklocation.split(os.path.sep)
                    if os.path.isabs(linklocation):
                        current_dir = current_dir._find_root().descend(*newpaths, follow_symlinks=True)
                    else:
                        current_dir = current_dir.descend(*newpaths, follow_symlinks=True)
                else:
                    raise VirtualDirectoryError(
                        "Cannot descend into '{}': '{}' is not a directory".format(path, new_path),
                        reason="not-a-directory",
                    )
            except FileNotFoundError:
                if create:
                    os.mkdir(new_path)
                    current_dir = FileBasedDirectory(new_path, parent=current_dir)
                else:
                    raise VirtualDirectoryError("Cannot descend into '{}': '{}' does not exist".format(path, new_path))

        return current_dir

    def import_files(
        self,
        external_pathspec,
        *,
        filter_callback=None,
        report_written=True,
        update_mtime=None,
        can_link=False,
        properties=None
    ):
        """ See superclass Directory for arguments """

        from ._casbaseddirectory import CasBasedDirectory  # pylint: disable=cyclic-import

        if isinstance(external_pathspec, CasBasedDirectory):
            if can_link:
                actionfunc = utils.safe_link
            else:
                actionfunc = utils.safe_copy

            import_result = FileListResult()
            self._import_files_from_cas(
                external_pathspec, actionfunc, filter_callback, update_mtime=update_mtime, result=import_result,
            )
        else:
            if isinstance(external_pathspec, Directory):
                source_directory = external_pathspec.external_directory
            else:
                source_directory = external_pathspec

            if can_link and not update_mtime:
                import_result = link_files(
                    source_directory,
                    self.external_directory,
                    filter_callback=filter_callback,
                    ignore_missing=False,
                    report_written=report_written,
                )
            else:
                import_result = copy_files(
                    source_directory,
                    self.external_directory,
                    filter_callback=filter_callback,
                    ignore_missing=False,
                    report_written=report_written,
                )
                if update_mtime:
                    for f in import_result.files_written:
                        os.utime(os.path.join(self.external_directory, f), times=(update_mtime, update_mtime))

        return import_result

    def import_single_file(self, external_pathspec, properties=None):
        dstpath = os.path.join(self.external_directory, os.path.basename(external_pathspec))
        result = FileListResult()
        if os.path.exists(dstpath):
            result.ignored.append(dstpath)
        else:
            shutil.copyfile(external_pathspec, dstpath, follow_symlinks=False)
        return result

    def _mark_changed(self):
        pass

    def set_deterministic_user(self):
        _set_deterministic_user(self.external_directory)

    def export_files(self, to_directory, *, can_link=False, can_destroy=False):
        if can_destroy:
            # Try a simple rename of the sandbox root; if that
            # doesnt cut it, then do the regular link files code path
            try:
                os.rename(self.external_directory, to_directory)
                return
            except OSError:
                # Proceed using normal link/copy
                pass

        os.makedirs(to_directory, exist_ok=True)
        if can_link:
            link_files(self.external_directory, to_directory)
        else:
            copy_files(self.external_directory, to_directory)

    # Add a directory entry deterministically to a tar file
    #
    # This function takes extra steps to ensure the output is deterministic.
    # First, it sorts the results of os.listdir() to ensure the ordering of
    # the files in the archive is the same.  Second, it sets a fixed
    # timestamp for each entry. See also https://bugs.python.org/issue24465.
    def export_to_tar(self, tarfile, destination_dir, mtime=BST_ARBITRARY_TIMESTAMP):
        # We need directories here, including non-empty ones,
        # so list_relative_paths is not used.
        for filename in sorted(os.listdir(self.external_directory)):
            source_name = os.path.join(self.external_directory, filename)
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
                self.descend(*filename.split(os.path.sep)).export_to_tar(tarfile, arcname, mtime)
            else:
                tarfile.addfile(tarinfo)

    def is_empty(self):
        it = os.scandir(self.external_directory)
        return next(it, None) is None

    def mark_unmodified(self):
        """ Marks all files in this directory (recursively) as unmodified.
        """
        _set_deterministic_mtime(self.external_directory)

    def list_modified_paths(self):
        """Provide a list of relative paths which have been modified since the
        last call to mark_unmodified.

        Return value: List(str) - list of modified paths
        """
        return [
            f
            for f in list_relative_paths(self.external_directory)
            if _get_link_mtime(os.path.join(self.external_directory, f)) != BST_ARBITRARY_TIMESTAMP
        ]

    def list_relative_paths(self):
        """Provide a list of all relative paths.

        Return value: List(str) - list of all paths
        """

        return list_relative_paths(self.external_directory)

    def get_size(self):
        return utils._get_dir_size(self.external_directory)

    def stat(self, *path, follow_symlinks=False):
        subdir = self.descend(*path[:-1], follow_symlinks=follow_symlinks)
        newpath = os.path.join(subdir.external_directory, path[-1])
        st = os.lstat(newpath)
        if follow_symlinks and stat.S_ISLNK(st.st_mode):
            linklocation = os.readlink(newpath)
            newpath = linklocation.split(os.path.sep)
            if os.path.isabs(linklocation):
                return subdir._find_root().stat(*newpath, follow_symlinks=True)
            return subdir.stat(*newpath, follow_symlinks=True)
        else:
            return st

    def exists(self, *path, follow_symlinks=False):
        try:
            self.stat(*path, follow_symlinks=follow_symlinks)
            return True
        except (VirtualDirectoryError, FileNotFoundError):
            return False

    def file_digest(self, *path):
        # Use descend() to avoid following symlinks (potentially escaping the sandbox)
        subdir = self.descend(*path[:-1])
        if subdir.exists(path[-1]) and not subdir.isfile(path[-1]):
            raise VirtualDirectoryError("Unsupported file type for digest")

        newpath = os.path.join(subdir.external_directory, path[-1])
        return utils.sha256sum(newpath)

    def readlink(self, *path):
        # Use descend() to avoid following symlinks (potentially escaping the sandbox)
        subdir = self.descend(*path[:-1])
        if subdir.exists(path[-1]) and not subdir.islink(path[-1]):
            raise VirtualDirectoryError("Unsupported file type for readlink")

        newpath = os.path.join(subdir.external_directory, path[-1])
        return os.readlink(newpath)

    def open_file(self, *path: str, mode: str = "r"):
        # Use descend() to avoid following symlinks (potentially escaping the sandbox)
        subdir = self.descend(*path[:-1])
        newpath = os.path.join(subdir.external_directory, path[-1])

        if mode not in ["r", "rb", "w", "wb", "w+", "w+b", "x", "xb", "x+", "x+b"]:
            raise ValueError("Unsupported mode: `{}`".format(mode))

        if "b" in mode:
            encoding = None
        else:
            encoding = "utf-8"

        if "r" in mode:
            return open(newpath, mode=mode, encoding=encoding)
        else:
            if "x" in mode:
                # This check is not atomic, however, we're operating with a
                # single thread in a private directory tree.
                if subdir.exists(path[-1]):
                    raise FileExistsError("{} already exists in {}".format(path[-1], str(subdir)))
                mode = "w" + mode[1:]

            return utils.save_file_atomic(newpath, mode=mode, encoding=encoding)

    def remove(self, *path, recursive=False):
        # Use descend() to avoid following symlinks (potentially escaping the sandbox)
        subdir = self.descend(*path[:-1])
        newpath = os.path.join(subdir.external_directory, path[-1])

        if subdir._get_filetype(path[-1]) == _FileType.DIRECTORY:
            if recursive:
                shutil.rmtree(newpath)
            else:
                os.rmdir(newpath)
        else:
            os.unlink(newpath)

    def rename(self, src, dest):
        # Use descend() to avoid following symlinks (potentially escaping the sandbox)
        srcdir = self.descend(*src[:-1])
        destdir = self.descend(*dest[:-1])
        srcpath = os.path.join(srcdir.external_directory, src[-1])
        destpath = os.path.join(destdir.external_directory, dest[-1])

        if destdir.exists(dest[-1]):
            destdir.remove(dest[-1])
        os.rename(srcpath, destpath)

    def __iter__(self):
        yield from os.listdir(self.external_directory)

    def __str__(self):
        # This returns the whole path (since we don't know where the directory started)
        # which exposes the sandbox directory; we will have to assume for the time being
        # that people will not abuse __str__.
        return self.external_directory

    def _get_underlying_directory(self) -> str:
        """ Returns the underlying (real) file system directory this
        object refers to. """
        return self.external_directory

    def _find_root(self):
        """ Finds the root of this directory tree by following 'parent' until there is
        no parent. """
        if self.parent:
            return self.parent._find_root()
        else:
            return self

    def _get_filetype(self, name=None):
        path = self.external_directory

        if name:
            path = os.path.join(path, name)

        st = os.lstat(path)
        if stat.S_ISDIR(st.st_mode):
            return _FileType.DIRECTORY
        elif stat.S_ISLNK(st.st_mode):
            return _FileType.SYMLINK
        elif stat.S_ISREG(st.st_mode):
            return _FileType.REGULAR_FILE
        else:
            return _FileType.SPECIAL_FILE

    def _import_files_from_cas(
        self, source_directory, actionfunc, filter_callback, *, path_prefix="", update_mtime=None, result
    ):
        """ Import files from a CAS-based directory. """

        for name, entry in source_directory.index.items():
            # The destination filename, relative to the root where the import started
            relative_pathname = os.path.join(path_prefix, name)

            # The full destination path
            dest_path = os.path.join(self.external_directory, name)

            is_dir = entry.type == _FileType.DIRECTORY

            if is_dir:
                src_subdir = source_directory.descend(name)

                try:
                    create_subdir = not os.path.lexists(dest_path)
                    dest_subdir = self.descend(name, create=create_subdir)
                except VirtualDirectoryError:
                    filetype = self._get_filetype(name)
                    raise VirtualDirectoryError(
                        "Destination is a {}, not a directory: /{}".format(filetype, relative_pathname)
                    )

                dest_subdir._import_files_from_cas(
                    src_subdir,
                    actionfunc,
                    filter_callback,
                    path_prefix=relative_pathname,
                    result=result,
                    update_mtime=update_mtime,
                )

            if filter_callback and not filter_callback(relative_pathname):
                if is_dir and create_subdir and dest_subdir.is_empty():
                    # Complete subdirectory has been filtered out, remove it
                    os.rmdir(dest_subdir.external_directory)

                # Entry filtered out, move to next
                continue

            if not is_dir:
                if os.path.lexists(dest_path):
                    # Collect overlaps
                    if not os.path.isdir(dest_path):
                        result.overwritten.append(relative_pathname)

                    if not utils.safe_remove(dest_path):
                        result.ignored.append(relative_pathname)
                        continue

                if entry.type == _FileType.REGULAR_FILE:
                    src_path = source_directory.cas_cache.objpath(entry.digest)

                    # fallback to copying if we require mtime support on this file
                    if update_mtime or entry.mtime is not None:
                        utils.safe_copy(src_path, dest_path, result=result)
                        mtime = update_mtime
                        # mtime property will override specified mtime
                        if entry.mtime is not None:
                            mtime = utils._parse_protobuf_timestamp(entry.mtime)
                        if mtime:
                            utils._set_file_mtime(dest_path, mtime)
                    else:
                        actionfunc(src_path, dest_path, result=result)

                    if entry.is_executable:
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

                else:
                    assert entry.type == _FileType.SYMLINK
                    os.symlink(entry.target, dest_path)
                result.files_written.append(relative_pathname)
