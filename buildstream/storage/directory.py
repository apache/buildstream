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

from .._exceptions import BstError, ErrorDomain
from ..utils import _magic_timestamp


class VirtualDirectoryError(BstError):
    """Raised by Directory functions when system calls fail.
    This will be handled internally by the BuildStream core,
    if you need to handle this error, then it should be reraised,
    or either of the :class:`.ElementError` or :class:`.SourceError`
    exceptions should be raised from this error.
    """
    def __init__(self, message, reason=None):
        super().__init__(message, domain=ErrorDomain.VIRTUAL_FS, reason=reason)


class Directory():
    def __init__(self, external_directory=None):
        raise NotImplementedError()

    def descend(self, subdirectory_spec, create=False):
        """Descend one or more levels of directory hierarchy and return a new
        Directory object for that directory.

        Args:
          subdirectory_spec (list of str): A list of strings which are all directory
            names.
          create (boolean): If this is true, the directories will be created if
            they don't already exist.

        Yields:
          A Directory object representing the found directory.

        Raises:
          VirtualDirectoryError: if any of the components in subdirectory_spec
            cannot be found, or are files, or symlinks to files.

        """
        raise NotImplementedError()

    # Import and export of files and links
    def import_files(self, external_pathspec, *, files=None,
                     report_written=True, update_utimes=False,
                     can_link=False):
        """Imports some or all files from external_path into this directory.

        Args:
          external_pathspec: Either a string containing a pathname, or a
            Directory object, to use as the source.
          files (list of str): A list of all the files relative to
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

        Yields:
          (FileListResult) - A report of files imported and overwritten.

        """

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

    def export_to_tar(self, tarfile, destination_dir, mtime=_magic_timestamp):
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

    def set_deterministic_mtime(self):
        """ Sets a static modification time for all regular files in this directory.
        The magic number for timestamps is 2011-11-11 11:11:11.
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
