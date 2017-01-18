#!/usr/bin/env python3
#
#  Copyright (C) 2016 Codethink Limited
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
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

import os
import errno
import stat
import shutil
import string
import collections
import hashlib
import pickle
from collections import OrderedDict
from . import _yaml
from . import ProgramNotFoundError


def list_relative_paths(directory, includedirs=False):
    """List relative filenames recursively

    Args:
       directory (str): The directory to list files in
       includedirs (bool): Whether to include directories in the returned list

    Returns:
       A sorted list of files in *directory*, relative to *directory*
    """
    filelist = []
    for (dirpath, _, filenames) in os.walk(directory):
        if includedirs:
            relpath = os.path.relpath(dirpath, directory)
            filelist.append(relpath)

        for f in filenames:
            fullpath = os.path.join(dirpath, f)
            relpath = os.path.relpath(fullpath, directory)
            filelist.append(relpath)

    return sorted(filelist)


def safe_copy(src, dest):
    """Copy a file while preserving attributes

    Args:
       src (str): The source filename
       dest (str): The destination filename

    This is almost the same as shutil.copy2(), except that
    we unlink *dest* before overwriting it if it exists, just
    incase *dest* is a hardlink to a different file.
    """
    # First unlink the target if it exists
    try:
        os.unlink(dest)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise e

    shutil.copy2(src, dest)


def safe_link(src, dest):
    """Try to create a hardlink, but resort to copying in the case of cross device links.

    Args:
       src (str): The source filename
       dest (str): The destination filename
    """

    # First unlink the target if it exists
    try:
        os.unlink(dest)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise e

    # If we can't link it due to cross-device hardlink, copy
    try:
        os.link(src, dest)
    except OSError as e:
        if e.errno == errno.EXDEV:
            shutil.copy2(src, dest)
        else:
            raise e


def copy_files(src, dest, files=None):
    """Copy files from source to destination.

    Args:
       src (str): The source file or directory
       dest (str): The destination directory
       files (list): List of source files to copy

    If *files* is not specified, then all files in *src*
    will be copied to *dest*
    """
    if not files:
        files = list_relative_paths(src, includedirs=True)

    # Use shutil.copy2() which uses copystat() to preserve attributes
    _process_list(src, dest, files, safe_copy)


def link_files(src, dest, files=None):
    """Hardlink files from source to destination.

    Args:
       src (str): The source file or directory
       dest (str): The destination directory
       files (list): List of source files to copy

    If *files* is not specified, then all files in *src*
    will be linked to *dest*.

    If the hardlink cannot be created due to crossing filesystems,
    then the file will be copied instead.
    """
    if not files:
        files = list_relative_paths(src, includedirs=True)

    _process_list(src, dest, files, safe_link)


def get_host_tool(name):
    """Get the full path of a host tool

    Args:
       name (str): The name of the program to search for

    Returns:
       The full path to the program, if found

    Raises:
       :class:`.ProgramNotFoundError`
    """
    search_path = os.environ.get('PATH')
    program_path = shutil.which(name, path=search_path)

    if not program_path:
        raise ProgramNotFoundError("Did not find '%s' in PATH: %s" % (name, search_path))

    return program_path


def url_directory_name(url):
    """Normalizes a url into a directory name

    Args:
       url (str): A url string

    Returns:
       A string which can be used as a directory name
    """
    valid_chars = string.digits + string.ascii_letters + '%_'

    def transl(x):
        return x if x in valid_chars else '_'

    return ''.join([transl(x) for x in url])


# Recursively make directories in target area and copy permissions
def _copy_directories(srcdir, destdir, target):
    dir = os.path.dirname(target)
    new_dir = os.path.join(destdir, dir)

    if not os.path.lexists(new_dir):
        if dir:
            _copy_directories(srcdir, destdir, dir)

        old_dir = os.path.join(srcdir, dir)
        if os.path.lexists(old_dir):
            dir_stat = os.lstat(old_dir)
            mode = dir_stat.st_mode

            if stat.S_ISDIR(mode) or stat.S_ISLNK(mode):
                os.makedirs(new_dir)
                shutil.copystat(old_dir, new_dir)
            else:
                raise OSError('Source directory tree has file where '
                              'directory expected: %s' % dir)


def _process_list(srcdir, destdir, filelist, actionfunc):

    def remove_if_exists(file_or_directory):
        if os.path.lexists(file_or_directory):
            # XXX We need to collect these to issue a report as a status message
            print("WARNING: Removing: {}".format(file_or_directory))
            try:
                os.unlink(file_or_directory)
            except OSError as e:
                if e.errno == errno.EISDIR:
                    shutil.rmtree(file_or_directory)
                else:
                    raise e

    for path in filelist:
        srcpath = os.path.join(srcdir, path)
        destpath = os.path.join(destdir, path)

        # The destination directory may not have been created separately
        _copy_directories(srcdir, destdir, path)

        # XXX os.lstat is known to raise UnicodeEncodeError
        file_stat = os.lstat(srcpath)
        mode = file_stat.st_mode

        if stat.S_ISDIR(mode):
            # Ensure directory exists in destination, then recurse.
            if not os.path.lexists(destpath):
                os.makedirs(destpath)
            dest_stat = os.stat(os.path.realpath(destpath))
            if not stat.S_ISDIR(dest_stat.st_mode):
                raise OSError('Destination not a directory. source has %s'
                              ' destination has %s' % (srcpath, destpath))
            shutil.copystat(srcpath, destpath)

        elif stat.S_ISLNK(mode):
            # Should we really nuke directories which symlinks replace ?
            # Should it be an error condition or just a warning ?
            # If a warning, should we drop the symlink instead ?
            remove_if_exists(destpath)
            target = os.readlink(srcpath)
            os.symlink(target, destpath)

        elif stat.S_ISREG(mode):

            # Process the file.
            remove_if_exists(destpath)
            actionfunc(srcpath, destpath)

        elif stat.S_ISCHR(mode) or stat.S_ISBLK(mode):

            # Block or character device. Put contents of st_dev in a mknod.
            remove_if_exists(destpath)
            if os.path.lexists(destpath):
                os.remove(destpath)
            os.mknod(destpath, file_stat.st_mode, file_stat.st_rdev)
            os.chmod(destpath, file_stat.st_mode)

        else:
            # Unsupported type.
            raise OSError('Cannot extract %s into staging-area. Unsupported type.' % srcpath)


# _relative_symlink_target()
#
# Fetches a relative path for symlink with an absolute target
#
# @root:    The staging area root location
# @symlink: Location of the symlink in staging area (including the root path)
# @target:  The symbolic link target, which may be an absolute path
#
# If @target is an absolute path, a relative path from the symbolic link
# location will be returned, otherwise if @target is a relative path, it will
# be returned unchanged.
#
# Using relative symlinks helps to keep the target self contained when staging
# files onto the target.
#
def _relative_symlink_target(root, symlink, target):

    if os.path.isabs(target):
        # First fix the input a little, the symlink itself must not have a
        # trailing slash, otherwise we fail to remove the symlink filename
        # from it's directory components in os.path.split()
        #
        # The absolute target filename must have it's leading separator
        # removed, otherwise os.path.join() will discard the prefix
        symlink = symlink.rstrip(os.path.sep)
        target = target.lstrip(os.path.sep)

        # We want a relative path from the directory in which symlink
        # is located, not from the symlink itself.
        symlinkdir, _ = os.path.split(symlink)

        # Create a full path to the target, including the leading staging
        # directory
        fulltarget = os.path.join(root, target)

        # now get the relative path from the directory where the symlink
        # is located within the staging root, to the target within the same
        # staging root
        newtarget = os.path.relpath(fulltarget, symlinkdir)

        return newtarget
    else:
        return target


# _generate_key()
#
# Generate an sha256 hex digest from the given value. The value
# can be a simple value or recursive dictionary with lists etc,
# anything simple enough to serialize.
#
# Args:
#    value: A value to get a key for
#
# Returns:
#    (str): An sha256 hex digest of the given value
#
def _generate_key(value):
    ordered = _node_sanitize(value)
    string = pickle.dumps(ordered)
    return hashlib.sha256(string).hexdigest()


# _node_sanitize()
#
# Returnes an alphabetically ordered recursive copy
# of the source node with internal provenance information stripped.
#
# Only dicts are ordered, list elements are left in order.
#
def _node_sanitize(node):

    if isinstance(node, collections.Mapping):

        result = OrderedDict()

        for key in sorted(node):
            if key == _yaml.PROVENANCE_KEY:
                continue
            result[key] = _node_sanitize(node[key])

        return result

    elif isinstance(node, list):
        return [_node_sanitize(elt) for elt in node]

    return node
