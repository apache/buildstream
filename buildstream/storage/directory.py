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
Directory
=========

Virtual Directory class to isolate the rest of BuildStream from the backing store implementation.
Sandboxes are allowed to read from and write to the underlying storage, but all others must use this
Directory class to access files and directories in the sandbox.

See also: :ref:`sandboxing`.
"""

from typing import List
from ..utils import FileListResult


class Directory():
    def __init__(self, external_directory=None):
        raise NotImplementedError()

    def descend(self, subdirectory_spec: List[str]) -> 'Directory':
        """
        Descend one or more levels of directory hierarchy and return a new
        Directory object for that directory.

        Arguments:
        subdirectory_spec (list of strings): A list of strings which are all directory
        names.
        create (boolean): If this is true, the directories will be created if
        they don't already exist.
        """
        raise NotImplementedError()

    # Import and export of files and links
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

        raise NotImplementedError()

    def export_files(self, to_directory: str, can_link: bool = False, can_destroy: bool = False) -> None:
        """Copies everything from this into to_directory.

        Arguments:

        to_directory (string): a path outside this directory object
        where the contents will be copied to.

        can_link (bool): Whether we can create hard links in to_directory
        instead of copying. Setting this does not guarantee hard links will be used.

        can_destroy (bool): Can we destroy the data already in this
        directory when exporting? If set, this may allow data to be
        moved rather than copied which will be quicker.
        """

        raise NotImplementedError()

    # Convenience functions
    def is_empty(self) -> bool:
        raise NotImplementedError()

    def set_deterministic_mtime(self) -> None:
        """ Sets a static modification time for all regular files in this directory.
        The magic number for timestamps: 2011-11-11 11:11:11
        """
        raise NotImplementedError()

    def set_deterministic_user(self) -> None:
        """ Sets all files in this directory to the current user's euid/egid.
        """
        raise NotImplementedError()

    def mark_unmodified(self) -> None:
        """ Marks all files in this directory (recursively) as unmodified.
        """
        raise NotImplementedError()

    def list_modified_paths(self) -> List[str]:
        """Provide a list of relative paths which have been modified since the
        last call to mark_unmodified.

        Return value: List(str) - dictionary with all paths
        """
        raise NotImplementedError()

    def list_relative_paths(self) -> List[str]:
        """Provide a list of all relative paths in this directory.

        Return value: List(str) - dictionary with all paths
        """
        raise NotImplementedError()

    def get_underlying_directory(self) -> str:
        """ Returns the underlying (real) file system directory this
        object refers to. This will throw an exception if there isn't
        a real directory behind the object. """
        raise NotImplementedError()
