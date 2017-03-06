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
import signal
from contextlib import contextmanager
from collections import OrderedDict, ChainMap, deque
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
    for (dirpath, dirnames, filenames) in os.walk(directory):

        if includedirs:
            for d in dirnames:
                fullpath = os.path.join(dirpath, d)
                relpath = os.path.relpath(fullpath, directory)
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


def _process_list(srcdir, destdir, filelist, actionfunc):

    def remove_if_exists(file_or_directory):
        if os.path.lexists(file_or_directory):

            # Try to remove anything that is in the way, but issue
            # a warning instead if it removes a non empty directory
            try:
                os.unlink(file_or_directory)
            except OSError as e:
                if e.errno != errno.EISDIR:
                    raise

                try:
                    os.rmdir(file_or_directory)
                except OSError as e:
                    if e.errno == errno.ENOTEMPTY:
                        print('WARNING: Ignoring symlink "' + destpath +
                              '" which purges non-empty directory')
                        return False
                    else:
                        raise

        return True

    for path in filelist:
        srcpath = os.path.join(srcdir, path)
        destpath = os.path.join(destdir, path)

        # The destination directory may not have been created separately
        _copy_directories(srcdir, destdir, path)

        # Ensure that broken symlinks to directories have their targets
        # created before attempting to stage files across broken
        # symlink boundaries
        _ensure_real_directory(destdir, os.path.dirname(destpath))

        # XXX os.lstat is known to raise UnicodeEncodeError
        file_stat = os.lstat(srcpath)
        mode = file_stat.st_mode

        if stat.S_ISDIR(mode):
            # Ensure directory exists in destination, then recurse.
            if not os.path.exists(destpath):
                _ensure_real_directory(destdir, destpath)

            dest_stat = os.lstat(os.path.realpath(destpath))
            if not stat.S_ISDIR(dest_stat.st_mode):
                raise OSError('Destination not a directory. source has %s'
                              ' destination has %s' % (srcpath, destpath))
            shutil.copystat(srcpath, destpath)

        elif stat.S_ISLNK(mode):
            # Should we really nuke directories which symlinks replace ?
            # Should it be an error condition or just a warning ?
            # If a warning, should we drop the symlink instead ?
            if not remove_if_exists(destpath):
                continue
            target = os.readlink(srcpath)
            target = _relative_symlink_target(destdir, destpath, target)
            os.symlink(target, destpath)

        elif stat.S_ISREG(mode):

            # Process the file.
            if not remove_if_exists(destpath):
                continue
            actionfunc(srcpath, destpath)

        elif stat.S_ISCHR(mode) or stat.S_ISBLK(mode):

            # Block or character device. Put contents of st_dev in a mknod.
            if not remove_if_exists(destpath):
                continue
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


def _node_chain_copy(source):
    copy = collections.ChainMap({}, source)
    for key, value in source.items():
        if isinstance(value, collections.Mapping):
            copy[key] = _node_chain_copy(value)
        elif isinstance(value, list):
            copy[key] = _list_chain_copy(value)
        elif isinstance(value, _yaml.Provenance):
            copy[key] = value.clone()

    return copy


def _list_chain_copy(source):
    copy = []
    for item in source:
        if isinstance(item, collections.Mapping):
            copy.append(_node_chain_copy(item))
        elif isinstance(item, list):
            copy.append(_list_chain_copy(item))
        elif isinstance(item, _yaml.Provenance):
            copy.append(item.clone())
        else:
            copy.append(item)

    return copy


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


# Global per process state for handling of sigterm, note that
# it is expected that this only ever be used by processes the
# scheduler forks off, not the main process
_terminator_stack = None


# The per-process SIGTERM handler
def _terminator_handler(signal, frame):
    while _terminator_stack:
        terminator = _terminator_stack.pop()
        terminator()
    exit(-1)


# _terminator()
#
# A context manager for interruptable tasks, this guarantees
# that while the code block is running, the supplied function
# will be called upon process termination.
#
# Args:
#    terminate_func (callable): A function to call when aborting
#                               the nested code block.
#
@contextmanager
def _terminator(terminate_func):
    global _terminator_stack

    if _terminator_stack is None:
        _terminator_stack = deque()

    outermost = False if _terminator_stack else True

    _terminator_stack.append(terminate_func)
    if outermost:
        original_handler = signal.signal(signal.SIGTERM, _terminator_handler)

    yield

    if outermost:
        signal.signal(signal.SIGTERM, original_handler)
    _terminator_stack.pop()


# A context manager for a code block which spawns a processes
# that becomes it's own session leader.
#
# In these cases, SIGSTP and SIGCONT need to be propagated to
# the child tasks, this is not expected to be used recursively,
# as the codeblock is expected to just spawn a processes.
#
@contextmanager
def _suspendable(suspend_callback, resume_callback):

    def _stop_handler(sig, frame):
        suspend_callback()

        # Propagate to default
        signal.signal(signal.SIGTSTP, original_stop)
        os.kill(os.getpid(), signal.SIGTSTP)
        signal.signal(signal.SIGTSTP, _stop_handler)

    def _cont_handler(sig, frame):
        resume_callback()

    original_cont = signal.signal(signal.SIGCONT, _cont_handler)
    original_stop = signal.signal(signal.SIGTSTP, _stop_handler)

    yield

    signal.signal(signal.SIGTSTP, original_stop)
    signal.signal(signal.SIGCONT, original_cont)
