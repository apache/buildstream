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
#        Jim MacArthur <jim.macarthur@codethink.co.uk>

"""
FileBasedDirectory
=========

Implementation of the Directory class which backs onto a normal POSIX filing system.

See also: :ref:`sandboxing`.
"""

from typing import List
from collections import OrderedDict

import calendar
import os
import time
from .._exceptions import BstError, ErrorDomain
from .directory import Directory
from ..utils import link_files, copy_files, FileListResult, list_relative_paths
from ..utils import _set_deterministic_user, _set_deterministic_mtime


class VirtualDirectoryError(BstError):
    """Raised by Directory functions when system calls fail.
    This will be handled internally by the BuildStream core,
    if you need to handle this error, then it should be reraised,
    or either of the :class:`.ElementError` or :class:`.SourceError`
    exceptions should be raised from this error.
    """
    def __init__(self, message, reason=None):
        super().__init__(message, domain=ErrorDomain.VIRTUAL_FS, reason=reason)


# Like os.path.getmtime(), but doesnt explode on symlinks
# Copy/pasted from compose.py
def getmtime(path):
    stat = os.lstat(path)
    return stat.st_mtime

# FileBasedDirectory intentionally doesn't call its superclass constuctor,
# which is mean to be unimplemented.
# pylint: disable=super-init-not-called


class _FileObject():
    """A description of a file in a virtual directory. The contents of
    this class are never used, but there needs to be something present
    for files so is_empty() works correctly.

    """
    def __init__(self, virtual_directory: Directory, filename: str):
        self.directory = virtual_directory
        self.filename = filename


class FileBasedDirectory(Directory):
    def __init__(self, external_directory=None):
        self.external_directory = external_directory
        self.index = OrderedDict()
        self._directory_read = False

    def _populate_index(self) -> None:
        if self._directory_read:
            return
        for entry in os.listdir(self.external_directory):
            if os.path.isdir(os.path.join(self.external_directory, entry)):
                self.index[entry] = FileBasedDirectory(os.path.join(self.external_directory, entry))
            else:
                self.index[entry] = _FileObject(self, entry)
        self._directory_read = True

    def descend(self, subdirectory_spec: List[str], create: bool = False) -> Directory:
        """ Descend one or more levels of directory hierarchy and return a new
        Directory object for that directory.

        Arguments:
        * subdirectory_spec (list of strings): A list of strings which are all directory
          names.
        * create (boolean): If this is true, the directories will be created if
          they don't already exist.
        """

        # It's very common to send a directory name instead of a list and this causes
        # bizarre errors, so check for it here
        if not isinstance(subdirectory_spec, list):
            subdirectory_spec = [subdirectory_spec]
        if not subdirectory_spec:
            return self

        # Because of the way split works, it's common to get a list which begins with
        # an empty string. Detect these and remove them, then start again.
        if subdirectory_spec[0] == "":
            return self.descend(subdirectory_spec[1:], create)

        # Forcibly re-read the directory.
        # TODO: This shouldn't be necessary. Any extra directories created using
        # 'descend' should have caused the index to be updated there, and we should
        # never need to call _populate_index again. Find out why.
        self._directory_read = False
        self._populate_index()

        if subdirectory_spec[0] in self.index:
            entry = self.index[subdirectory_spec[0]]
            if isinstance(entry, FileBasedDirectory):
                new_path = os.path.join(self.external_directory, subdirectory_spec[0])
                return FileBasedDirectory(new_path).descend(subdirectory_spec[1:], create)
            else:
                error = "Cannot descend into {}, which is a '{}' in the directory {}"
                raise VirtualDirectoryError(error.format(subdirectory_spec[0],
                                                         type(entry).__name__,
                                                         self.external_directory))
        else:
            if create:
                new_path = os.path.join(self.external_directory, subdirectory_spec[0])
                os.makedirs(new_path, exist_ok=True)
                return FileBasedDirectory(new_path).descend(subdirectory_spec[1:], create)
            else:
                error = "No entry called '{}' found in the directory rooted at {}"
                raise VirtualDirectoryError(error.format(subdirectory_spec[0], self.external_directory))
        return None

    def import_files(self, external_pathspec: any, files: List[str] = None,
                     report_written: bool = True, update_utimes: bool = False,
                     can_link: bool = False) -> FileListResult:
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

        update_utimes (bool): Update the access and modification time
        of each file copied to the current time.

        can_link (bool): Whether it's OK to create a hard link to the
        original content, meaning the stored copy will change when the
        original files change. Setting this doesn't guarantee hard
        links will be made. can_link will never be used if
        update_utimes is set.
        """

        if isinstance(external_pathspec, Directory):
            source_directory = external_pathspec.external_directory
        else:
            source_directory = external_pathspec

        if can_link and not update_utimes:
            import_result = link_files(source_directory, self.external_directory, files=files,
                                       ignore_missing=False, report_written=report_written)
        else:
            import_result = copy_files(source_directory, self.external_directory, files=files,
                                       ignore_missing=False, report_written=report_written)
        if update_utimes:
            cur_time = time.time()

            for f in import_result.files_written:
                os.utime(os.path.join(self.external_directory, f), times=(cur_time, cur_time))
        return import_result

    def set_deterministic_mtime(self) -> None:
        """ Sets a static modification time for all regular files in this directory.
        The magic number for timestamps: 2011-11-11 11:11:11
        """
        _set_deterministic_mtime(self.external_directory)

    def set_deterministic_user(self) -> None:
        """ Sets all files in this directory to the current user's euid/egid.
        """
        _set_deterministic_user(self.external_directory)

    def export_files(self, to_directory: str, can_link: bool = False, can_destroy: bool = False) -> None:
        """Copies everything from this into to_directory.

        Arguments:

        to_directory (string): a path outside this directory object
        where the contents will be copied to.

        can_link (bool): Whether we can create hard links in to_directory
        instead of copying.

        """

        if can_destroy:
            # Try a simple rename of the sandbox root; if that
            # doesnt cut it, then do the regular link files code path
            try:
                os.rename(self.external_directory, to_directory)
                return
            except OSError:
                # Proceed using normal link/copy
                pass

        if can_link:
            link_files(self.external_directory, to_directory)
        else:
            copy_files(self.external_directory, to_directory)

    def is_empty(self) -> bool:
        """ Return true if this directory has no files, subdirectories or links in it.
        """
        self._populate_index()
        return len(self.index) == 0

    def mark_unmodified(self) -> None:
        """ Marks all files in this directory (recursively) as unmodified.
        """
        _set_deterministic_mtime(self.external_directory)

    def list_modified_paths(self) -> List[str]:
        """Provide a list of relative paths which have been modified since the
        last call to mark_unmodified.

        Return value: List(str) - list of modified paths
        """
        magic_timestamp = calendar.timegm([2011, 11, 11, 11, 11, 11])

        return [f for f in list_relative_paths(self.external_directory)
                if getmtime(os.path.join(self.external_directory, f)) != magic_timestamp]

    def list_relative_paths(self) -> List[str]:
        """Provide a list of all relative paths.

        Return value: List(str) - list of all paths
        """

        return list_relative_paths(self.external_directory)

    def __str__(self) -> str:
        # This returns the whole path (since we don't know where the directory started)
        # which exposes the sandbox directory; we will have to assume for the time being
        # that people will not abuse __str__.
        return self.external_directory

    def get_underlying_directory(self) -> str:
        """ Returns the underlying (real) file system directory this
        object refers to. """
        return self.external_directory
