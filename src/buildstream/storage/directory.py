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

"""
Directory - Interfacing with files
==================================
The Directory class is given to plugins by way of the :class:`.Sandbox`
and in some other instances. This API allows plugins to interface with files
and directory hierarchies owned by BuildStream.


.. _directory_path:

Paths
-----
The path argument to directory functions depict a relative path. Path elements are
separated with the ``/`` character regardless of the platform. Both ``.`` and ``..`` entries
are permitted. Absolute paths are not permitted, as such it is illegal to specify a path
with a leading ``/`` character.

Directory objects represent a directory entry within the context of a *directory tree*,
and the directory returned by
:func:`Sandbox.get_virtual_directory() <buildstream.sandbox.Sandbox.get_virtual_directory>`
is the root of the sandbox's *directory tree*. Attempts to escape the root of a *directory tree*
using ``..`` entries will not result in an error, instead ``..`` entries which cross the
root boundary will be evaluated as the root directory. This behavior matches POSIX behavior
of filesystem root directories.
"""


from contextlib import contextmanager
from tarfile import TarFile
from typing import Callable, Optional, Union, List, IO, Iterator

from .._exceptions import BstError
from ..exceptions import ErrorDomain
from ..utils import BST_ARBITRARY_TIMESTAMP, FileListResult
from ..types import FastEnum


class DirectoryError(BstError):
    """Raised by Directory functions.

    It is recommended to handle this error and raise a more descriptive
    user facing :class:`.ElementError` or :class:`.SourceError` from this error.

    If this is not handled, the BuildStream core will fail the current
    task where the error occurs and present the user with the error.
    """

    def __init__(self, message: str, reason: str = None):
        super().__init__(message, domain=ErrorDomain.VIRTUAL_FS, reason=reason)


class FileType(FastEnum):
    """Depicts the type of a file"""

    DIRECTORY: int = 1
    """A directory"""

    REGULAR_FILE: int = 2
    """A regular file"""

    SYMLINK: int = 3
    """A symbolic link"""

    def __str__(self):
        # https://github.com/PyCQA/pylint/issues/2062
        return self.name.lower().replace("_", " ")  # pylint: disable=no-member


class FileStat:
    """Depicts stats about a file

    .. note::

       This object can be compared with the equality operator, two :class:`.FileStat`
       objects will be considered equivalent if they have the same :class:`.FileType`
       and have equivalent attributes.
    """

    def __init__(
        self, file_type: int, *, executable: bool = False, size: int = 0, mtime: float = BST_ARBITRARY_TIMESTAMP
    ) -> None:

        self.file_type: int = file_type
        """The :class:`.FileType` of this file"""

        self.executable: bool = executable
        """Whether this file is executable"""

        self.size: int = size
        """The size of the file in bytes"""

        self.mtime: float = mtime
        """The modification time of the file"""

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FileStat):
            return NotImplemented

        return (
            self.file_type == other.file_type
            and self.executable == other.file_type
            and self.size == other.size
            and self.mtime == other.mtime
        )


class Directory:
    """The Directory object represents a directory in a filesystem hierarchy

    .. tip::

       Directory objects behave as a collection of entries in the pythonic sense.
       Iterating over a directory will yield the entries, and a directory is
       truthy if it contains any entries and falsy if it is empty.
    """

    def __init__(self, external_directory=None):
        raise NotImplementedError()

    def __iter__(self) -> Iterator[str]:
        raise NotImplementedError()

    def __len__(self) -> int:
        raise NotImplementedError()

    ###################################################################
    #                           Public API                            #
    ###################################################################

    def open_directory(self, path: str, *, create: bool = False, follow_symlinks: bool = False) -> "Directory":
        """Open a Directory object relative to this directory

        Args:
           path: A :ref:`path <directory_path>` relative to this directory.
           create: If this is true, the directories will be created if
                   they don't already exist.

        Returns:
           A Directory object representing the found directory.

        Raises:
           DirectoryError: if any of the components in subdirectory_spec
                           cannot be found, or are files, or symlinks to files.
        """
        raise NotImplementedError()

    # Import and export of files and links
    def import_files(
        self,
        external_pathspec: Union["Directory", str],
        *,
        filter_callback: Optional[Callable[[str], bool]] = None,
        collect_result: bool = True
    ) -> Optional[FileListResult]:
        """Imports some or all files from external_path into this directory.

        Args:
           external_pathspec: Either a string containing a pathname, or a
                              Directory object, to use as the source.
           filter_callback: Optional filter callback. Called with the
                            relative path as argument for every file in the source directory.
                            The file is imported only if the callable returns True.
                            If no filter callback is specified, all files will be imported.
           collect_result: Whether to collect data for the :class:`.FileListResult`, defaults to True.

        Returns:
           A :class:`.FileListResult` report of files imported and overwritten,
           or `None` if `collect_result` is False.

        Raises:
           DirectoryError: if any system error occurs.
        """
        return self._import_files_internal(
            external_pathspec,
            filter_callback=filter_callback,
            collect_result=collect_result,
        )

    def import_single_file(self, external_pathspec: str) -> FileListResult:
        """Imports a single file from an external path

        Args:
           external_pathspec: A string containing a pathname.
           properties: Optional list of strings representing file properties to capture when importing.

        Returns:
           A :class:`.FileListResult` report of files imported and overwritten.

        Raises:
           DirectoryError: if any system error occurs.
        """
        raise NotImplementedError()

    def export_to_tar(self, tarfile: TarFile, destination_dir: str, mtime: int = BST_ARBITRARY_TIMESTAMP) -> None:
        """Exports this directory into the given tar file.

        Args:
          tarfile: A Python TarFile object to export into.
          destination_dir: The prefix for all filenames inside the archive.
          mtime: mtimes of all files in the archive are set to this.

        Raises:
           DirectoryError: if any system error occurs.
        """
        raise NotImplementedError()

    def list_relative_paths(self) -> Iterator[str]:
        """Generate a list of all relative paths in this directory.

        Yields:
           All files in this directory with relative paths.
        """
        raise NotImplementedError()

    def exists(self, path: str, *, follow_symlinks: bool = False) -> bool:
        """Check whether the specified path exists.

        Args:
           path: A :ref:`path <directory_path>` relative to this directory.
           follow_symlinks: True to follow symlinks.

        Returns:
           True if the path exists, False otherwise.
        """
        raise NotImplementedError()

    def stat(self, path: str, *, follow_symlinks: bool = False) -> FileStat:
        """Get the status of a file.

        Args:
           path: A :ref:`path <directory_path>` relative to this directory.
           follow_symlinks: True to follow symlinks.

        Returns:
           A :class:`.FileStat` object.

        Raises:
           DirectoryError: if any system error occurs.
        """
        raise NotImplementedError()

    @contextmanager
    def open_file(self, path: str, *, mode: str = "r") -> Iterator[IO]:
        """Open file and return a corresponding file object. In text mode,
        UTF-8 is used as encoding.

        Args:
           path: A :ref:`path <directory_path>` relative to this directory.
           mode (str): An optional string that specifies the mode in which the file is opened.

        Yields:
           The file object for the open file

        Raises:
           DirectoryError: if any system error occurs.
        """
        raise NotImplementedError()

    def file_digest(self, path: str) -> str:
        """Return a unique digest of a file.

        Args:
           path: A :ref:`path <directory_path>` relative to this directory.

        Raises:
           DirectoryError: if the specified *path* depicts an entry that is not a
                           :attr:`.FileType.REGULAR_FILE`, or if any system error occurs.
        """
        raise NotImplementedError()

    def readlink(self, path: str) -> str:
        """Return a string representing the path to which the symbolic link points.

        Args:
           path: A :ref:`path <directory_path>` relative to this directory.

        Returns:
           The path to which the symbolic link points to.

        Raises:
           DirectoryError: if any system error occurs.
        """
        raise NotImplementedError()

    def remove(self, path: str, *, recursive: bool = False) -> None:
        """Remove a file, symlink or directory. Symlinks are not followed.

        Args:
           path: A :ref:`path <directory_path>` relative to this directory.
           recursive: True to delete non-empty directories.

        Raises:
           DirectoryError: if any system error occurs.
        """
        raise NotImplementedError()

    def rename(self, src: str, dest: str) -> None:
        """Rename a file, symlink or directory. If destination path exists
        already and is a file or empty directory, it will be replaced.

        Args:
           src: A source :ref:`path <directory_path>` relative to this directory.
           dest: A destination :ref:`path <directory_path>` relative to this directory.

        Raises:
           DirectoryError: if any system error occurs.
        """
        raise NotImplementedError()

    def isfile(self, path: str, *, follow_symlinks: bool = False) -> bool:
        """Check whether the specified path is an existing regular file.

        Args:
           path: A :ref:`path <directory_path>` relative to this directory.
           follow_symlinks: True to follow symlinks.

        Returns:
           True if the path is an existing regular file, False otherwise.
        """
        try:
            st = self.stat(path, follow_symlinks=follow_symlinks)
            return st.file_type == FileType.REGULAR_FILE
        except DirectoryError:
            return False

    def isdir(self, path: str, *, follow_symlinks: bool = False) -> bool:
        """Check whether the specified path is an existing directory.

        Args:
           path: A :ref:`path <directory_path>` relative to this directory.
           follow_symlinks: True to follow symlinks.

        Returns:
           True if the path is an existing directory, False otherwise.
        """
        try:
            st = self.stat(path, follow_symlinks=follow_symlinks)
            return st.file_type == FileType.DIRECTORY
        except DirectoryError:
            return False

    def islink(self, path: str, *, follow_symlinks: bool = False) -> bool:
        """Check whether the specified path is an existing symlink.

        Args:
           path: A :ref:`path <directory_path>` relative to this directory.
           follow_symlinks: True to follow symlinks.

        Returns:
           True if the path is an existing symlink, False otherwise.
        """
        try:
            st = self.stat(path, follow_symlinks=follow_symlinks)
            return st.file_type == FileType.SYMLINK
        except DirectoryError:
            return False

    ###################################################################
    #                         Internal API                            #
    ###################################################################

    # _import_files_internal()
    #
    # Internal API for importing files, which exposes a few more parameters than
    # the public API exposes.
    #
    # Args:
    #   external_pathspec: Either a string containing a pathname, or a
    #                      Directory object, to use as the source.
    #   filter_callback: Optional filter callback. Called with the
    #                    relative path as argument for every file in the source directory.
    #                    The file is imported only if the callable returns True.
    #                    If no filter callback is specified, all files will be imported.
    #                    update_mtime: Update the access and modification time of each file copied to the time specified in seconds.
    #   properties: Optional list of strings representing file properties to capture when importing.
    #   collect_result: Whether to collect data for the :class:`.FileListResult`, defaults to True.
    #
    # Returns:
    #    A :class:`.FileListResult` report of files imported and overwritten,
    #    or `None` if `collect_result` is False.
    #
    # Raises:
    #    DirectoryError: if any system error occurs.
    #
    def _import_files_internal(
        self,
        external_pathspec: Union["Directory", str],
        *,
        filter_callback: Optional[Callable[[str], bool]] = None,
        update_mtime: Optional[float] = None,
        properties: Optional[List[str]] = None,
        collect_result: bool = True
    ) -> Optional[FileListResult]:
        return self._import_files(
            external_pathspec,
            filter_callback=filter_callback,
            update_mtime=update_mtime,
            properties=properties,
            collect_result=collect_result,
        )

    # _import_files()
    #
    # Abstract method for backends to import files from an external directory
    #
    # Args:
    #   external_pathspec: Either a string containing a pathname, or a
    #                      Directory object, to use as the source.
    #   filter_callback: Optional filter callback. Called with the
    #                    relative path as argument for every file in the source directory.
    #                    The file is imported only if the callable returns True.
    #                    If no filter callback is specified, all files will be imported.
    #                    update_mtime: Update the access and modification time of each file copied to the time specified in seconds.
    #   properties: Optional list of strings representing file properties to capture when importing.
    #   collect_result: Whether to collect data for the :class:`.FileListResult`, defaults to True.
    #
    # Returns:
    #    A :class:`.FileListResult` report of files imported and overwritten,
    #    or `None` if `collect_result` is False.
    #
    # Raises:
    #    DirectoryError: if any system error occurs.
    #
    def _import_files(
        self,
        external_pathspec: Union["Directory", str],
        *,
        filter_callback: Optional[Callable[[str], bool]] = None,
        update_mtime: Optional[float] = None,
        properties: Optional[List[str]] = None,
        collect_result: bool = True
    ) -> Optional[FileListResult]:
        raise NotImplementedError()

    # _export_files()
    #
    # Exports everything from this directory into to_directory.
    #
    # Args:
    #    to_directory: a path outside this directory object where the contents will be copied to.
    #    can_link: Whether we can create hard links in to_directory instead of copying.
    #              Setting this does not guarantee hard links will be used.
    #    can_destroy: Can we destroy the data already in this directory when exporting? If set,
    #                 this may allow data to be moved rather than copied which will be quicker.
    #
    # Raises:
    #    DirectoryError: if any system error occurs.
    #
    def _export_files(self, to_directory: str, *, can_link: bool = False, can_destroy: bool = False) -> None:
        raise NotImplementedError()

    # _get_underlying_path()
    #
    # Args:
    #    filename: The name of the file in this directory
    #
    # Returns the underlying (real) file system path for the file in this
    # directory
    #
    # Raises:
    #    DirectoryError: if the backend doesn't use local files, or if
    #                    there is no such file in this directory
    #
    def _get_underlying_path(self, filename) -> str:
        raise NotImplementedError()

    # _get_underlying_directory()
    #
    # Returns the underlying (real) file system directory this
    # object refers to.
    #
    # Raises:
    #    DirectoryError: if the backend doesn't have an underlying directory
    #
    def _get_underlying_directory(self) -> str:
        raise NotImplementedError()

    # _set_deterministic_user():
    #
    # Abstract method to set all files in this directory to the current user's euid/egid.
    #
    def _set_deterministic_user(self):
        raise NotImplementedError()

    # _get_size()
    #
    # Get an approximation of the storage space in bytes used by this directory
    # and all files and subdirectories in it. Storage space varies by implementation
    # and effective space used may be lower than this number due to deduplication.
    #
    def _get_size(self) -> int:
        raise NotImplementedError()

    # _create_empty_file()
    #
    # Utility function to create an empty file
    #
    def _create_empty_file(self, path: str) -> None:
        with self.open_file(path, mode="w"):
            pass

    # _validate_path()
    #
    # Convenience function for backends to validate path input
    #
    def _validate_path(self, path: str) -> None:
        if path and path[0] == "/":
            raise ValueError("Invalid path '{}'".format(path))
