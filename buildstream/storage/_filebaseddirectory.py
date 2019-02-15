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
import time
from .directory import Directory, VirtualDirectoryError
from ..utils import link_files, copy_files, list_relative_paths, _get_link_mtime, _magic_timestamp
from ..utils import _set_deterministic_user, _set_deterministic_mtime

# FileBasedDirectory intentionally doesn't call its superclass constuctor,
# which is meant to be unimplemented.
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
        self.index = {}
        self._directory_read = False

    def _populate_index(self):
        if self._directory_read:
            return
        for entry in os.listdir(self.external_directory):
            if os.path.isdir(os.path.join(self.external_directory, entry)):
                self.index[entry] = FileBasedDirectory(os.path.join(self.external_directory, entry))
            else:
                self.index[entry] = _FileObject(self, entry)
        self._directory_read = True

    def descend(self, subdirectory_spec, create=False):
        """ See superclass Directory for arguments """
        # It's very common to send a directory name instead of a list and this causes
        # bizarre errors, so check for it here
        if not isinstance(subdirectory_spec, list):
            subdirectory_spec = [subdirectory_spec]

        # Because of the way split works, it's common to get a list which begins with
        # an empty string. Detect these and remove them.
        while subdirectory_spec and subdirectory_spec[0] == "":
            subdirectory_spec.pop(0)

        if not subdirectory_spec:
            return self

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
                self.index[subdirectory_spec[0]] = FileBasedDirectory(new_path).descend(subdirectory_spec[1:], create)
                return self.index[subdirectory_spec[0]]
            else:
                error = "No entry called '{}' found in the directory rooted at {}"
                raise VirtualDirectoryError(error.format(subdirectory_spec[0], self.external_directory))

    def import_files(self, external_pathspec, *, files=None,
                     report_written=True, update_utimes=False,
                     can_link=False):
        """ See superclass Directory for arguments """

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
        self._mark_changed()
        return import_result

    def _mark_changed(self):
        self._directory_read = False

    def set_deterministic_mtime(self):
        _set_deterministic_mtime(self.external_directory)

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
    def export_to_tar(self, tf, dir_arcname, mtime=_magic_timestamp):
        # We need directories here, including non-empty ones,
        # so list_relative_paths is not used.
        for filename in sorted(os.listdir(self.external_directory)):
            source_name = os.path.join(self.external_directory, filename)
            arcname = os.path.join(dir_arcname, filename)
            tarinfo = tf.gettarinfo(source_name, arcname)
            tarinfo.mtime = mtime

            if tarinfo.isreg():
                with open(source_name, "rb") as f:
                    tf.addfile(tarinfo, f)
            elif tarinfo.isdir():
                tf.addfile(tarinfo)
                self.descend(filename.split(os.path.sep)).export_to_tar(tf, arcname, mtime)
            else:
                tf.addfile(tarinfo)

    def is_empty(self):
        self._populate_index()
        return len(self.index) == 0

    def mark_unmodified(self):
        """ Marks all files in this directory (recursively) as unmodified.
        """
        _set_deterministic_mtime(self.external_directory)

    def list_modified_paths(self):
        """Provide a list of relative paths which have been modified since the
        last call to mark_unmodified.

        Return value: List(str) - list of modified paths
        """
        return [f for f in list_relative_paths(self.external_directory)
                if _get_link_mtime(os.path.join(self.external_directory, f)) != _magic_timestamp]

    def list_relative_paths(self):
        """Provide a list of all relative paths.

        Return value: List(str) - list of all paths
        """

        return list_relative_paths(self.external_directory)

    def __str__(self):
        # This returns the whole path (since we don't know where the directory started)
        # which exposes the sandbox directory; we will have to assume for the time being
        # that people will not abuse __str__.
        return self.external_directory

    def _get_underlying_directory(self) -> str:
        """ Returns the underlying (real) file system directory this
        object refers to. """
        return self.external_directory
