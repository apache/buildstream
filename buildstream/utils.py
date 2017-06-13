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
import calendar
import psutil
from . import ProgramNotFoundError
from . import _yaml


def list_relative_paths(directory):
    """A generator for walking directory relative paths

    This generator is useful for checking the full manifest of
    a directory.

    Note that only empty directories will be yielded.

    Symbolic links will not be followed, but will be included
    in the manifest.

    Args:
       directory (str): The directory to list files in

    Yields:
       Relative filenames in `directory`
    """
    for (dirpath, dirnames, filenames) in os.walk(directory):
        # os.walk does not decend into symlink directories, which
        # makes sense because otherwise we might have redundant
        # directories, or end up descending into directories outside
        # of the walk() directory.
        #
        # But symlinks to directories are still identified as
        # subdirectories in the walked `dirpath`, so we extract
        # these symlinks from `dirnames`
        #
        for d in dirnames:
            fullpath = os.path.join(dirpath, d)
            if os.path.islink(fullpath):
                relpath = os.path.relpath(fullpath, directory)
                yield relpath

        # We've decended into an empty directory, in this case we
        # want to include the directory itself, but not in any other
        # case.
        if not filenames:
            relpath = os.path.relpath(dirpath, directory)
            yield relpath

        # List the filenames in the walked directory
        for f in filenames:
            fullpath = os.path.join(dirpath, f)
            relpath = os.path.relpath(fullpath, directory)
            yield relpath


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


def safe_move(src, dest):
    """Move a file while preserving attributes

    Args:
       src (str): The source filename
       dest (str): The destination filename

    This is almost the same as shutil.move(), except that
    we unlink *dest* before overwriting it if it exists, just
    incase *dest* is a hardlink to a different file.
    """
    # First unlink the target if it exists
    try:
        os.unlink(dest)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise e

    shutil.move(src, dest)


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


def safe_remove(path):
    """Removes a file or directory

    This will remove a file if it exists, and will
    remove a directory if the directory is not empty.

    Args:
       path (str): The path to remove

    Returns:
       True if `path` was removed or did not exist, False
       if `path` was a non empty directory.

    Raises:
        OSError: If any other system error occured
    """
    if os.path.lexists(path):

        # Try to remove anything that is in the way, but issue
        # a warning instead if it removes a non empty directory
        try:
            os.unlink(path)
        except OSError as e:
            if e.errno != errno.EISDIR:
                raise

            try:
                os.rmdir(path)
            except OSError as e:
                if e.errno == errno.ENOTEMPTY:
                    return False
                else:
                    raise

    return True


def copy_files(src, dest, files=None, ignore_missing=False):
    """Copy files from source to destination.

    Args:
       src (str): The source file or directory
       dest (str): The destination directory
       files (list): Optional list of files in `src` to copy
       ignore_missing (bool): Dont raise any error if a source file is missing

    Returns:
       This returns two lists, the first list contains any files which
       were overwritten in `dest` and the second list contains any
       files which were not copied as they would replace a non empty
       directory in `dest`

    Note::

      Directories in `dest` are replaced with files from `src`,
      unless the existing directory in `dest` is not empty in which
      case the path will be reported in the return value.
    """
    if files is None:
        files = list_relative_paths(src)

    # Use shutil.copy2() which uses copystat() to preserve attributes
    return _process_list(src, dest, files, safe_copy, ignore_missing=ignore_missing)


def move_files(src, dest, files=None, ignore_missing=False):
    """Move files from source to destination.

    Args:
       src (str): The source file or directory
       dest (str): The destination directory
       files (list): Optional list of files in `src` to move
       ignore_missing (bool): Dont raise any error if a source file is missing

    Returns:
       This returns two lists, the first list contains any files which
       were overwritten in `dest` and the second list contains any
       files which were not moved as they would replace a non empty
       directory in `dest`

    Note::

      Directories in `dest` are replaced with files from `src`,
      unless the existing directory in `dest` is not empty in which
      case the path will be reported in the return value.
    """
    if files is None:
        files = list_relative_paths(src)

    # Use shutil.move() which uses copystat() to preserve attributes
    return _process_list(src, dest, files, safe_move, ignore_missing=ignore_missing)


def link_files(src, dest, files=None, ignore_missing=False):
    """Hardlink files from source to destination.

    Args:
       src (str): The source file or directory
       dest (str): The destination directory
       files (list): Optional list of files in `src` to link
       ignore_missing (bool): Dont raise any error if a source file is missing

    Returns:
       This returns two lists, the first list contains any files which
       were overwritten in `dest` and the second list contains any
       files which were not moved as they would replace a non empty
       directory in `dest`

    Note::

      Directories in `dest` are replaced with files from `src`,
      unless the existing directory in `dest` is not empty in which
      case the path will be reported in the return value.

    Note::

      If a hardlink cannot be created due to crossing filesystems,
      then the file will be copied instead.
    """
    if files is None:
        files = list_relative_paths(src)

    return _process_list(src, dest, files, safe_link, ignore_missing=ignore_missing)


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
    this_dir = os.path.dirname(target)
    new_dir = os.path.join(destdir, this_dir)

    if not os.path.lexists(new_dir):
        if this_dir:
            _copy_directories(srcdir, destdir, this_dir)

        old_dir = os.path.join(srcdir, this_dir)
        if os.path.lexists(old_dir):
            dir_stat = os.lstat(old_dir)
            mode = dir_stat.st_mode

            if stat.S_ISDIR(mode) or stat.S_ISLNK(mode):
                os.makedirs(new_dir)
                shutil.copystat(old_dir, new_dir)
            else:
                raise OSError('Source directory tree has file where '
                              'directory expected: %s' % dir)


def _ensure_real_directory(root, destpath):
    # The realpath in the sandbox may refer to a file outside of the
    # sandbox when any of the direcory branches are a symlink to an
    # absolute path.
    #
    # This should not happen as we rely on relative_symlink_target() below
    # when staging the actual symlinks which may lead up to this path.
    #
    realpath = os.path.realpath(destpath)
    if not realpath.startswith(os.path.realpath(root)):
        raise IOError('Destination path resolves to a path outside ' +
                      'of the staging area\n\n' +
                      '  Destination path: %s\n' % destpath +
                      '  Real path: %s' % realpath)

    # Ensure the real destination path exists before trying to get the mode
    # of the real destination path.
    #
    # It is acceptable that chunks create symlinks inside artifacts which
    # refer to non-existing directories, they will be created on demand here
    # at staging time.
    #
    if not os.path.exists(realpath):
        os.makedirs(realpath)

    return realpath


# _process_list()
#
# Internal helper for copying/moving/linking file lists
#
# This will handle directories, symlinks and special files
# internally, the `actionfunc` will only be called for regular files.
#
# Args:
#    srcdir: The source base directory
#    destdir: The destination base directory
#    filelist: List of relative file paths
#    actionfunc: The function to call for regular files
#    ignore_missing: Dont raise any error if a source file is missing
#
# Returns:
#    (list): Overwritten files
#    (list): Ignored overwritten files
#
def _process_list(srcdir, destdir, filelist, actionfunc, ignore_missing=False):

    # Note we consume the filelist (which is a generator and not a list)
    # by sorting it, this is necessary to ensure that we processes symbolic
    # links which lead to directories before processing files inside those
    # directories.
    #
    overwrites = []
    ignored = []
    for path in sorted(filelist):
        srcpath = os.path.join(srcdir, path)
        destpath = os.path.join(destdir, path)

        # Collect overlaps
        if os.path.lexists(destpath) and not os.path.isdir(destpath):
            overwrites.append(path)

        # The destination directory may not have been created separately
        _copy_directories(srcdir, destdir, path)

        # Ensure that broken symlinks to directories have their targets
        # created before attempting to stage files across broken
        # symlink boundaries
        _ensure_real_directory(destdir, os.path.dirname(destpath))

        try:
            file_stat = os.lstat(srcpath)
            mode = file_stat.st_mode
        except FileNotFoundError:
            # Skip this missing file
            if ignore_missing:
                continue
            else:
                raise

        if stat.S_ISDIR(mode):
            # Ensure directory exists in destination
            if not os.path.exists(destpath):
                _ensure_real_directory(destdir, destpath)

            dest_stat = os.lstat(os.path.realpath(destpath))
            if not stat.S_ISDIR(dest_stat.st_mode):
                raise OSError('Destination not a directory. source has %s'
                              ' destination has %s' % (srcpath, destpath))
            shutil.copystat(srcpath, destpath)

        elif stat.S_ISLNK(mode):
            if not safe_remove(destpath):
                ignored.append(path)
                continue

            target = os.readlink(srcpath)
            target = _relative_symlink_target(destdir, destpath, target)
            os.symlink(target, destpath)

        elif stat.S_ISREG(mode):
            # Process the file.
            if not safe_remove(destpath):
                ignored.append(path)
                continue

            actionfunc(srcpath, destpath)

        elif stat.S_ISCHR(mode) or stat.S_ISBLK(mode):
            # Block or character device. Put contents of st_dev in a mknod.
            if not safe_remove(destpath):
                ignored.append(path)
                continue

            if os.path.lexists(destpath):
                os.remove(destpath)
            os.mknod(destpath, file_stat.st_mode, file_stat.st_rdev)
            os.chmod(destpath, file_stat.st_mode)

        else:
            # Unsupported type.
            raise OSError('Cannot extract %s into staging-area. Unsupported type.' % srcpath)

    return (overwrites, ignored)


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
        # from its directory components in os.path.split()
        #
        # The absolute target filename must have its leading separator
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
    ordered = _yaml.node_sanitize(value)
    string = pickle.dumps(ordered)
    return hashlib.sha256(string).hexdigest()


# _set_deterministic_mtime()
#
# Set the mtime for every file in a directory tree to the same.
#
# Args:
#    directory (str): The directory to recursively set the mtime on
#
def _set_deterministic_mtime(directory):
    # The magic number for timestamps: 2011-11-11 11:11:11
    magic_timestamp = calendar.timegm([2011, 11, 11, 11, 11, 11])

    for dirname, _, filenames in os.walk(directory.encode("utf-8"), topdown=False):
        for filename in filenames:
            pathname = os.path.join(dirname, filename)

            # Python's os.utime only ever modifies the timestamp
            # of the target, it is not acceptable to set the timestamp
            # of the target here, if we are staging the link target we
            # will also set its timestamp.
            #
            # We should however find a way to modify the actual link's
            # timestamp, this outdated python bug report claims that
            # it is impossible:
            #
            #   http://bugs.python.org/issue623782
            #
            # However, nowadays it is possible at least on gnuish systems
            # with with the lutimes glibc function.
            if not os.path.islink(pathname):
                os.utime(pathname, (magic_timestamp, magic_timestamp))

        os.utime(dirname, (magic_timestamp, magic_timestamp))


# _kill_process_tree()
#
# Brutally murder a process and all of it's children
#
# Args:
#    pid (int): Process ID
#
def _kill_process_tree(pid):
    proc = psutil.Process(pid)
    children = proc.children(recursive=True)

    def kill_proc(p):
        try:
            p.kill()
        except psutil.AccessDenied:
            # Ignore this error, it can happen with
            # some setuid bwrap processes.
            pass

    # Bloody Murder
    for child in children:
        kill_proc(child)
    kill_proc(proc)
