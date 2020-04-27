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
Directory
=========

This is a virtual Directory class to isolate the rest of BuildStream
from the backing store implementation.  Sandboxes are allowed to read
from and write to the underlying storage, but all others must use this
Directory class to access files and directories in the sandbox.

See also: :ref:`sandboxing`.

"""


import os
import stat
from typing import Callable, Optional, Union, List

from .._exceptions import BstError
from ..exceptions import ErrorDomain
from ..types import FastEnum
from ..utils import BST_ARBITRARY_TIMESTAMP, FileListResult


class VirtualDirectoryError(BstError):
    """Raised by Directory functions when system calls fail.
    This will be handled internally by the BuildStream core,
    if you need to handle this error, then it should be reraised,
    or either of the :class:`.ElementError` or :class:`.SourceError`
    exceptions should be raised from this error.
    """

    def __init__(self, message, reason=None):
        super().__init__(message, domain=ErrorDomain.VIRTUAL_FS, reason=reason)


class Directory:
    def __init__(self, external_directory=None):
        raise NotImplementedError()

    def descend(self, *paths: str, create: bool = False, follow_symlinks: bool = False):
        """Descend one or more levels of directory hierarchy and return a new
        Directory object for that directory.

        Args:
          *paths: A list of strings which are all directory names.
          create: If this is true, the directories will be created if
            they don't already exist.

        Yields:
          A Directory object representing the found directory.

        Raises:
          VirtualDirectoryError: if any of the components in subdirectory_spec
            cannot be found, or are files, or symlinks to files.

        """
        raise NotImplementedError()

    # Import and export of files and links
    def import_files(
        self,
        external_pathspec: Union["Directory", str],
        *,
        filter_callback: Optional[Callable[[str], bool]] = None,
        report_written: bool = True,
        update_mtime: Optional[float] = None,
        can_link: bool = False,
        properties: Optional[List[str]] = None
    ) -> FileListResult:
        """Imports some or all files from external_path into this directory.

        Args:
          external_pathspec: Either a string containing a pathname, or a
            Directory object, to use as the source.
          filter_callback: Optional filter callback. Called with the
            relative path as argument for every file in the source directory.
            The file is imported only if the callable returns True.
            If no filter callback is specified, all files will be imported.
          report_written: Return the full list of files
            written. Defaults to true. If false, only a list of
            overwritten files is returned.
          update_mtime: Update the access and modification time
            of each file copied to the time specified in seconds.
          can_link: Whether it's OK to create a hard link to the
            original content, meaning the stored copy will change when the
            original files change. Setting this doesn't guarantee hard
            links will be made.
          properties: Optional list of strings representing file properties
            to capture when importing.

        Yields:
          A report of files imported and overwritten.

        """

        raise NotImplementedError()

    def import_single_file(self, external_pathspec, properties=None):
        """Imports a single file from an external path"""
        raise NotImplementedError()

    def export_files(self, to_directory, *, can_link=False, can_destroy=False):
        """Copies everything from this into to_directory.

        Args:
          to_directory (string): a path outside this directory object
            where the contents will be copied to.
          can_link (bool): Whether we can create hard links in to_directory
            instead of copying. Setting this does not guarantee hard links will be used.
          can_destroy (bool): Can we destroy the data already in this
            directory when exporting? If set, this may allow data to be
            moved rather than copied which will be quicker.
        """

        raise NotImplementedError()

    def export_to_tar(self, tarfile, destination_dir, mtime=BST_ARBITRARY_TIMESTAMP):
        """ Exports this directory into the given tar file.

        Args:
          tarfile (TarFile): A Python TarFile object to export into.
          destination_dir (str): The prefix for all filenames inside the archive.
          mtime (int): mtimes of all files in the archive are set to this.
        """
        raise NotImplementedError()

    # Convenience functions
    def is_empty(self):
        """ Return true if this directory has no files, subdirectories or links in it.
        """
        raise NotImplementedError()

    def set_deterministic_user(self):
        """ Sets all files in this directory to the current user's euid/egid.
        """
        raise NotImplementedError()

    def mark_unmodified(self):
        """ Marks all files in this directory (recursively) as unmodified.
        """
        raise NotImplementedError()

    def list_modified_paths(self):
        """Provide a list of relative paths which have been modified since the
        last call to mark_unmodified. Includes directories only if
        they are empty.

        Yields:
          (List(str)) - list of all modified files with relative paths.

        """
        raise NotImplementedError()

    def list_relative_paths(self):
        """Provide a list of all relative paths in this directory. Includes
        directories only if they are empty.

        Yields:
          (List(str)) - list of all files with relative paths.

        """
        raise NotImplementedError()

    def _mark_changed(self):
        """Internal function to mark this directory as having been changed
        outside this API. This normally can only happen by calling the
        Sandbox's `run` method. This does *not* mark everything as modified
        (i.e. list_modified_paths will not necessarily return the same results
        as list_relative_paths after calling this.)

        """
        raise NotImplementedError()

    def get_size(self):
        """ Get an approximation of the storage space in bytes used by this directory
        and all files and subdirectories in it. Storage space varies by implementation
        and effective space used may be lower than this number due to deduplication. """
        raise NotImplementedError()

    def exists(self, *paths: str, follow_symlinks: bool = False) -> bool:
        """ Check whether the specified path exists.

        Args:
          *paths: A list of strings which are all path components.
          follow_symlinks: True to follow symlinks.

        Returns:
          True if the path exists, False otherwise.
        """
        raise NotImplementedError()

    def stat(self, *paths: str, follow_symlinks: bool = False) -> os.stat_result:
        """ Get the status of a file.

        Args:
          *paths: A list of strings which are all path components.
          follow_symlinks: True to follow symlinks.

        Returns:
          A `os.stat_result` object.
        """
        raise NotImplementedError()

    def isfile(self, *paths: str, follow_symlinks: bool = False) -> bool:
        """ Check whether the specified path is an existing regular file.

        Args:
          *paths: A list of strings which are all path components.
          follow_symlinks: True to follow symlinks.

        Returns:
          True if the path is an existing regular file, False otherwise.
        """
        try:
            st = self.stat(*paths, follow_symlinks=follow_symlinks)
            return stat.S_ISREG(st.st_mode)
        except (VirtualDirectoryError, FileNotFoundError):
            return False

    def isdir(self, *paths: str, follow_symlinks: bool = False) -> bool:
        """ Check whether the specified path is an existing directory.

        Args:
          *paths: A list of strings which are all path components.
          follow_symlinks: True to follow symlinks.

        Returns:
          True if the path is an existing directory, False otherwise.
        """
        try:
            st = self.stat(*paths, follow_symlinks=follow_symlinks)
            return stat.S_ISDIR(st.st_mode)
        except (VirtualDirectoryError, FileNotFoundError):
            return False

    def islink(self, *paths: str, follow_symlinks: bool = False) -> bool:
        """ Check whether the specified path is an existing symlink.

        Args:
          *paths: A list of strings which are all path components.
          follow_symlinks: True to follow symlinks.

        Returns:
          True if the path is an existing symlink, False otherwise.
        """
        try:
            st = self.stat(*paths, follow_symlinks=follow_symlinks)
            return stat.S_ISLNK(st.st_mode)
        except (VirtualDirectoryError, FileNotFoundError):
            return False

    def open_file(self, *paths: str, mode: str = "r"):
        """ Open file and return a corresponding file object. In text mode,
        UTF-8 is used as encoding.

        Args:
          *paths: A list of strings which are all path components.
          mode (str): An optional string that specifies the mode in which the file is opened.
        """
        raise NotImplementedError()

    def file_digest(self, *paths: str) -> str:
        """ Return a digest of a file. The digest algorithm is implementation-
        defined.

        Args:
          *paths: A list of strings which are all path components.
        """
        raise NotImplementedError()

    def readlink(self, *paths: str) -> str:
        """ Return a string representing the path to which the symbolic link points.

        Args:
          *paths: A list of strings which are all path components.
        """
        raise NotImplementedError()

    def remove(self, *paths: str, recursive: bool = False):
        """ Remove a file, symlink or directory. Symlinks are not followed.

        Args:
          *paths: A list of strings which are all path components.
          recursive: True to delete non-empty directories.
        """
        raise NotImplementedError()

    def rename(self, src: List[str], dest: List[str]):
        """ Rename a file, symlink or directory. If destination path exists
        already and is a file or empty directory, it will be replaced.

        Args:
          *src: Source path components.
          *dest: Destination path components.
        """
        raise NotImplementedError()

    def _create_empty_file(self, *paths):
        with self.open_file(*paths, mode="w"):
            pass


# FileType:
#
# Type of file or directory entry.
#
class _FileType(FastEnum):

    # Directory
    DIRECTORY = 1

    # Regular file
    REGULAR_FILE = 2

    # Symbolic link
    SYMLINK = 3

    # Special file (FIFO, character device, block device, or socket)
    SPECIAL_FILE = 4

    def __str__(self):
        # https://github.com/PyCQA/pylint/issues/2062
        return self.name.lower().replace("_", " ")  # pylint: disable=no-member
