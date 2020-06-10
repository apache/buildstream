#
#  Copyright (C) 2016-2018 Codethink Limited
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
"""
Utilities
=========
"""

import calendar
import errno
import hashlib
import math
import os
import re
import shutil
import signal
import stat
from stat import S_ISDIR
import subprocess
import tempfile
import time
import datetime
import itertools
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, IO, Iterable, Iterator, Optional, Tuple, Union
from dateutil import parser as dateutil_parser
from google.protobuf import timestamp_pb2

import psutil

from . import _signals
from ._exceptions import BstError
from .exceptions import ErrorDomain
from ._protos.build.bazel.remote.execution.v2 import remote_execution_pb2

# Contains utils that have been rewritten in Cython for speed benefits
# This makes them available when importing from utils
from ._utils import url_directory_name  # pylint: disable=unused-import

# The magic number for timestamps: 2011-11-11 11:11:11
BST_ARBITRARY_TIMESTAMP = calendar.timegm((2011, 11, 11, 11, 11, 11))

# The separator we use for user specified aliases
_ALIAS_SEPARATOR = ":"
_URI_SCHEMES = ["http", "https", "ftp", "file", "git", "sftp", "ssh"]

# Main process pid
_MAIN_PID = os.getpid()

# The number of threads in the main process at startup.
# This is 1 except for certain test environments (xdist/execnet).
_INITIAL_NUM_THREADS_IN_MAIN_PROCESS = 1

# Number of seconds to wait for background threads to exit.
_AWAIT_THREADS_TIMEOUT_SECONDS = 5

# The process's file mode creation mask.
# Impossible to retrieve without temporarily changing it on POSIX.
_UMASK = os.umask(0o777)
os.umask(_UMASK)


class UtilError(BstError):
    """Raised by utility functions when system calls fail.

    This will be handled internally by the BuildStream core,
    if you need to handle this error, then it should be reraised,
    or either of the :class:`.ElementError` or :class:`.SourceError`
    exceptions should be raised from this error.
    """

    def __init__(self, message, reason=None):
        super().__init__(message, domain=ErrorDomain.UTIL, reason=reason)


class ProgramNotFoundError(BstError):
    """Raised if a required program is not found.

    It is normally unneeded to handle this exception from plugin code.
    """

    def __init__(self, message, reason=None):
        super().__init__(message, domain=ErrorDomain.PROG_NOT_FOUND, reason=reason)


class DirectoryExistsError(OSError):
    """Raised when a `os.rename` is attempted but the destination is an existing directory.
    """


class FileListResult:
    """An object which stores the result of one of the operations
    which run on a list of files.
    """

    def __init__(self):

        self.overwritten = []
        """List of files which were overwritten in the target directory"""

        self.ignored = []
        """List of files which were ignored, because they would have
        replaced a non empty directory"""

        self.failed_attributes = []
        """List of files for which attributes could not be copied over"""

        self.files_written = []
        """List of files that were written."""


def _make_timestamp(timepoint: float) -> str:
    """Obtain the ISO 8601 timestamp represented by the time given in seconds.

    Args:
        timepoint (float): the time since the epoch in seconds

    Returns:
        (str): the timestamp specified by https://www.ietf.org/rfc/rfc3339.txt
               with a UTC timezone code 'Z'.

    """
    assert isinstance(timepoint, float), "Time to render as timestamp must be a float: {}".format(str(timepoint))
    try:
        return datetime.datetime.utcfromtimestamp(timepoint).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    except (OverflowError, TypeError):
        raise UtilError("Failed to make UTC timestamp from {}".format(timepoint))


def _get_file_mtimestamp(fullpath: str) -> str:
    """Obtain the ISO 8601 timestamp represented by the mtime of the
    file at the given path."""
    assert isinstance(fullpath, str), "Path to file must be a string: {}".format(str(fullpath))
    try:
        mtime = os.path.getmtime(fullpath)
    except OSError:
        raise UtilError("Failed to get mtime of file at {}".format(fullpath))
    return _make_timestamp(mtime)


def _parse_timestamp(timestamp: str) -> float:
    """Parse an ISO 8601 timestamp as specified in
    https://www.ietf.org/rfc/rfc3339.txt. Only timestamps with the UTC code
    'Z' or an offset are valid. For example: '2019-12-12T10:23:01.54Z' or
    '2019-12-12T10:23:01.54+00:00'.

    Args:
        timestamp (str): the timestamp

    Returns:
        (float): The time in seconds since epoch represented by the
            timestamp.

    Raises:
        UtilError: if extraction of seconds fails
    """
    assert isinstance(timestamp, str), "Timestamp to parse must be a string: {}".format(str(timestamp))
    try:
        errmsg = "Failed to parse given timestamp: " + timestamp
        parsed_time = dateutil_parser.isoparse(timestamp)
        if parsed_time.tzinfo:
            return parsed_time.timestamp()
        raise UtilError(errmsg)
    except (ValueError, OverflowError, TypeError):
        raise UtilError(errmsg)


def _make_protobuf_timestamp(timestamp: timestamp_pb2.Timestamp, timepoint: float):
    """Obtain the Protobuf Timestamp represented by the time given in seconds.

    Args:
        timestamp: the Protobuf Timestamp to set
        timepoint: the time since the epoch in seconds

    """
    timestamp.seconds = int(timepoint)
    timestamp.nanos = int(math.modf(timepoint)[0] * 1e9)


def _get_file_protobuf_mtimestamp(timestamp: timestamp_pb2.Timestamp, fullpath: str):
    """Obtain the Protobuf Timestamp represented by the mtime of the
    file at the given path."""
    assert isinstance(fullpath, str), "Path to file must be a string: {}".format(str(fullpath))
    try:
        mtime = os.path.getmtime(fullpath)
    except OSError:
        raise UtilError("Failed to get mtime of file at {}".format(fullpath))
    _make_protobuf_timestamp(timestamp, mtime)


def _parse_protobuf_timestamp(timestamp: timestamp_pb2.Timestamp) -> float:
    """Convert Protobuf Timestamp to seconds since epoch.

    Args:
        timestamp: the Protobuf Timestamp

    Returns:
        The time in seconds since epoch represented by the timestamp.
    """
    return timestamp.seconds + timestamp.nanos / 1e9


def _set_file_mtime(fullpath: str, seconds: Union[int, float]) -> None:
    """Set the access and modification times of the file at the given path
    to the given time. The time of the file will be set with nanosecond
    resolution if supported.

    Args:
        fullpath (str): the string representing the path to the file
        timestamp (int, float): the time in seconds since the UNIX epoch
    """
    assert isinstance(fullpath, str), "Path to file must be a string: {}".format(str(fullpath))
    assert isinstance(seconds, (int, float)), "Mtime to set must be a float or integer: {}".format(str(seconds))
    set_mtime = seconds * 10 ** 9
    try:
        os.utime(fullpath, times=None, ns=(int(set_mtime), int(set_mtime)))
    except OSError:
        errmsg = "Failed to set the times of the file at {} to {}".format(fullpath, str(seconds))
        raise UtilError(errmsg)


def list_relative_paths(directory: str) -> Iterator[str]:
    """A generator for walking directory relative paths

    This generator is useful for checking the full manifest of
    a directory.

    Symbolic links will not be followed, but will be included
    in the manifest.

    Args:
       directory: The directory to list files in

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
        # these symlinks from `dirnames` and add them to `filenames`.
        #
        for d in dirnames:
            fullpath = os.path.join(dirpath, d)
            if os.path.islink(fullpath):
                filenames.append(d)

        # Modifying the dirnames directly ensures that the os.walk() generator
        # allows us to specify the order in which they will be iterated.
        dirnames.sort()
        filenames.sort()

        relpath = os.path.relpath(dirpath, directory)

        # We don't want "./" pre-pended to all the entries in the root of
        # `directory`, prefer to have no prefix in that case.
        basepath = relpath if relpath != "." and dirpath != directory else ""

        # First yield the walked directory itself, except for the root
        if basepath != "":
            yield basepath

        # List the filenames in the walked directory
        for f in filenames:
            yield os.path.join(basepath, f)


# pylint: disable=anomalous-backslash-in-string
def glob(paths: Iterable[str], pattern: str) -> Iterator[str]:
    """A generator to yield paths which match the glob pattern

    Args:
       paths (iterable): The paths to check
       pattern (str): A glob pattern

    This generator will iterate over the passed *paths* and
    yield only the filenames which matched the provided *pattern*.

    +--------+------------------------------------------------------------------+
    | Meta   | Description                                                      |
    +========+==================================================================+
    | \*     | Zero or more of any character, excepting path separators         |
    +--------+------------------------------------------------------------------+
    | \**    | Zero or more of any character, including path separators         |
    +--------+------------------------------------------------------------------+
    | ?      | One of any character, except for path separators                 |
    +--------+------------------------------------------------------------------+
    | [abc]  | One of any of the specified characters                           |
    +--------+------------------------------------------------------------------+
    | [a-z]  | One of the characters in the specified range                     |
    +--------+------------------------------------------------------------------+
    | [!abc] | Any single character, except the specified characters            |
    +--------+------------------------------------------------------------------+
    | [!a-z] | Any single character, except those in the specified range        |
    +--------+------------------------------------------------------------------+

    .. note::

       Escaping of the metacharacters is not possible

    """
    # Ensure leading slash, just because we want patterns
    # to match file lists regardless of whether the patterns
    # or file lists had a leading slash or not.
    if not pattern.startswith(os.sep):
        pattern = os.sep + pattern

    expression = _glob2re(pattern)
    regexer = re.compile(expression)

    for filename in paths:
        filename_try = filename
        if not filename_try.startswith(os.sep):
            filename_try = os.sep + filename_try

        if regexer.match(filename_try):
            yield filename


def sha256sum(filename: str) -> str:
    """Calculate the sha256sum of a file

    Args:
       filename: A path to a file on disk

    Returns:
      An sha256 checksum string

    Raises:
       UtilError: In the case there was an issue opening
                  or reading `filename`
    """
    try:
        h = hashlib.sha256()
        with open(filename, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)

    except OSError as e:
        raise UtilError("Failed to get a checksum of file '{}': {}".format(filename, e)) from e

    return h.hexdigest()


def safe_copy(src: str, dest: str, *, copystat: bool = True, result: Optional[FileListResult] = None) -> None:
    """Copy a file while optionally preserving attributes

    Args:
       src: The source filename
       dest: The destination filename
       copystat: Whether to preserve attributes
       result: An optional collective result

    Raises:
       UtilError: In the case of unexpected system call failures

    This is almost the same as shutil.copy2() when copystat is True,
    except that we unlink *dest* before overwriting it if it exists, just
    incase *dest* is a hardlink to a different file.
    """
    # First unlink the target if it exists
    try:
        os.unlink(dest)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise UtilError("Failed to remove destination file '{}': {}".format(dest, e)) from e

    try:
        shutil.copyfile(src, dest)
    except (OSError, shutil.Error) as e:
        raise UtilError("Failed to copy '{} -> {}': {}".format(src, dest, e)) from e

    if copystat:
        try:
            shutil.copystat(src, dest)
        except PermissionError:
            # If we failed to copy over some file stats, dont treat
            # it as an unrecoverable error, but provide some feedback
            # we can use for a warning.
            #
            # This has a tendency of happening when attempting to copy
            # over extended file attributes.
            if result:
                result.failed_attributes.append(dest)


def safe_link(src: str, dest: str, *, result: Optional[FileListResult] = None, _unlink=False) -> None:
    """Try to create a hardlink, but resort to copying in the case of cross device links.

    Args:
       src: The source filename
       dest: The destination filename
       result: An optional collective result

    Raises:
       UtilError: In the case of unexpected system call failures
    """

    if _unlink:
        # First unlink the target if it exists
        try:
            os.unlink(dest)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise UtilError("Failed to remove destination file '{}': {}".format(dest, e)) from e

    # If we can't link it due to cross-device hardlink, copy
    try:
        os.link(src, dest)
    except OSError as e:
        if e.errno == errno.EEXIST and not _unlink:
            # Target exists already, unlink and try again
            safe_link(src, dest, result=result, _unlink=True)
        elif e.errno == errno.EXDEV or e.errno == errno.EPERM:
            safe_copy(src, dest)
        else:
            raise UtilError("Failed to link '{} -> {}': {}".format(src, dest, e)) from e


def safe_remove(path: str) -> bool:
    """Removes a file or directory

    This will remove a file if it exists, and will
    remove a directory if the directory is empty.

    Args:
       path: The path to remove

    Returns:
       True if `path` was removed or did not exist, False
       if `path` was a non empty directory.

    Raises:
       UtilError: In the case of unexpected system call failures
    """
    try:
        if S_ISDIR(os.lstat(path).st_mode):
            os.rmdir(path)
        else:
            os.unlink(path)

        # File removed/unlinked successfully
        return True

    except OSError as e:
        if e.errno == errno.ENOTEMPTY:
            # Path is non-empty directory
            return False
        elif e.errno == errno.ENOENT:
            # Path does not exist
            return True

        raise UtilError("Failed to remove '{}': {}".format(path, e))


def copy_files(
    src: str,
    dest: str,
    *,
    filter_callback: Optional[Callable[[str], bool]] = None,
    ignore_missing: bool = False,
    report_written: bool = False
) -> FileListResult:
    """Copy files from source to destination.

    Args:
       src: The source directory
       dest: The destination directory
       filter_callback: Optional filter callback. Called with the relative path as
                        argument for every file in the source directory. The file is
                        copied only if the callable returns True. If no filter callback
                        is specified, all files will be copied.
       ignore_missing: Dont raise any error if a source file is missing
       report_written: Add to the result object the full list of files written

    Returns:
       The result describing what happened during this file operation

    Raises:
       UtilError: In the case of unexpected system call failures

    .. note::

       Directories in `dest` are replaced with files from `src`,
       unless the existing directory in `dest` is not empty in which
       case the path will be reported in the return value.

       UNIX domain socket files from `src` are ignored.
    """
    result = FileListResult()
    try:
        _process_list(
            src,
            dest,
            safe_copy,
            result,
            filter_callback=filter_callback,
            ignore_missing=ignore_missing,
            report_written=report_written,
        )
    except OSError as e:
        raise UtilError("Failed to copy '{} -> {}': {}".format(src, dest, e))
    return result


def link_files(
    src: str,
    dest: str,
    *,
    filter_callback: Optional[Callable[[str], bool]] = None,
    ignore_missing: bool = False,
    report_written: bool = False
) -> FileListResult:
    """Hardlink files from source to destination.

    Args:
       src: The source directory
       dest: The destination directory
       filter_callback: Optional filter callback. Called with the relative path as
                        argument for every file in the source directory. The file is
                        hardlinked only if the callable returns True. If no filter
                        callback is specified, all files will be hardlinked.
       ignore_missing: Dont raise any error if a source file is missing
       report_written: Add to the result object the full list of files written

    Returns:
       The result describing what happened during this file operation

    Raises:
       UtilError: In the case of unexpected system call failures

    .. note::

       Directories in `dest` are replaced with files from `src`,
       unless the existing directory in `dest` is not empty in which
       case the path will be reported in the return value.

    .. note::

       If a hardlink cannot be created due to crossing filesystems,
       then the file will be copied instead.

       UNIX domain socket files from `src` are ignored.
    """
    result = FileListResult()
    try:
        _process_list(
            src,
            dest,
            safe_link,
            result,
            filter_callback=filter_callback,
            ignore_missing=ignore_missing,
            report_written=report_written,
        )
    except OSError as e:
        raise UtilError("Failed to link '{} -> {}': {}".format(src, dest, e))

    return result


def get_host_tool(name: str) -> str:
    """Get the full path of a host tool

    Args:
       name (str): The name of the program to search for

    Returns:
       The full path to the program, if found

    Raises:
       :class:`.ProgramNotFoundError`
    """
    search_path = os.environ.get("PATH")
    program_path = shutil.which(name, path=search_path)

    if not program_path:
        raise ProgramNotFoundError("Did not find '{}' in PATH: {}".format(name, search_path))

    return program_path


def get_bst_version() -> Tuple[int, int]:
    """Gets the major, minor release portion of the
    BuildStream version.

    Returns:
       A 2-tuple of form (major version, minor version)
    """
    # Import this only conditionally, it's not resolved at bash complete time
    from . import __version__  # pylint: disable=cyclic-import

    versions = __version__.split(".")[:2]

    if versions[0] == "0+untagged":
        raise UtilError(
            "Your git repository has no tags - BuildStream can't "
            "determine its version. Please run `git fetch --tags`."
        )

    try:
        return _parse_version(__version__)
    except UtilError as e:
        raise UtilError("Failed to detect BuildStream version: {}\n".format(e)) from e


def move_atomic(source: Union[Path, str], destination: Union[Path, str], *, ensure_parents: bool = True) -> None:
    """Move the source to the destination using atomic primitives.

    This uses `os.rename` to move a file or directory to a new destination.
    It wraps some `OSError` thrown errors to ensure their handling is correct.

    The main reason for this to exist is that rename can throw different errors
    for the same symptom (https://www.unix.com/man-page/POSIX/3posix/rename/)
    when we are moving a directory.

    We are especially interested here in the case when the destination already
    exists, is a directory and is not empty. In this case, either EEXIST or
    ENOTEMPTY can be thrown.

    In order to ensure consistent handling of these exceptions, this function
    should be used instead of `os.rename`

    Args:
      source: source to rename
      destination: destination to which to move the source
      ensure_parents: Whether or not to create the parent's directories
                      of the destination (default: True)
    Raises:
      DirectoryExistsError: if the destination directory already exists and is
                            not empty
      OSError: if another filesystem level error occured
    """
    if ensure_parents:
        os.makedirs(os.path.dirname(str(destination)), exist_ok=True)

    try:
        os.rename(str(source), str(destination))
    except OSError as exc:
        if exc.errno in (errno.EEXIST, errno.ENOTEMPTY):
            raise DirectoryExistsError(*exc.args) from exc
        raise


@contextmanager
def save_file_atomic(
    filename: str,
    mode: str = "w",
    *,
    buffering: int = -1,
    encoding: Optional[str] = None,
    errors: Optional[str] = None,
    newline: Optional[str] = None,
    closefd: bool = True,
    opener: Optional[Callable[[str, int], int]] = None,
    tempdir: Optional[str] = None
) -> Iterator[IO]:
    """Save a file with a temporary name and rename it into place when ready.

    This is a context manager which is meant for saving data to files.
    The data is written to a temporary file, which gets renamed to the target
    name when the context is closed. This avoids readers of the file from
    getting an incomplete file.

    **Example:**

    .. code:: python

      with save_file_atomic('/path/to/foo', 'w') as f:
          f.write(stuff)

    The file will be called something like ``tmpCAFEBEEF`` until the
    context block ends, at which point it gets renamed to ``foo``. The
    temporary file will be created in the same directory as the output file.
    The ``filename`` parameter must be an absolute path.

    If an exception occurs or the process is terminated, the temporary file will
    be deleted.
    """
    # This feature has been proposed for upstream Python in the past, e.g.:
    # https://bugs.python.org/issue8604

    assert os.path.isabs(filename), "The utils.save_file_atomic() parameter ``filename`` must be an absolute path"
    if tempdir is None:
        tempdir = os.path.dirname(filename)
    fd, tempname = tempfile.mkstemp(dir=tempdir)
    # Apply mode allowed by umask
    os.fchmod(fd, 0o666 & ~_UMASK)
    os.close(fd)

    f = open(
        tempname,
        mode=mode,
        buffering=buffering,
        encoding=encoding,
        errors=errors,
        newline=newline,
        closefd=closefd,
        opener=opener,
    )

    def cleanup_tempfile():
        f.close()
        try:
            os.remove(tempname)
        except FileNotFoundError:
            pass
        except OSError as e:
            raise UtilError("Failed to cleanup temporary file {}: {}".format(tempname, e)) from e

    try:
        with _signals.terminator(cleanup_tempfile):
            # Disable type-checking since "IO[Any]" has no attribute "real_filename"
            f.real_filename = filename  # type: ignore
            yield f
            f.close()
            # This operation is atomic, at least on platforms we care about:
            # https://bugs.python.org/issue8828
            os.replace(tempname, filename)
    except Exception:
        cleanup_tempfile()
        raise


# get_umask():
#
# Get the process's file mode creation mask without changing it.
#
# Returns:
#     (int) The process's file mode creation mask.
#
def get_umask():
    return _UMASK


# _get_dir_size():
#
# Get the disk usage of a given directory in bytes.
#
# This function assumes that files do not inadvertantly
# disappear while this function is running.
#
# Arguments:
#     (str) The path whose size to check.
#
# Returns:
#     (int) The size on disk in bytes.
#
def _get_dir_size(path):
    path = os.path.abspath(path)

    def get_size(path):
        total = 0

        for f in os.scandir(path):
            total += f.stat(follow_symlinks=False).st_size

            if f.is_dir(follow_symlinks=False):
                total += get_size(f.path)

        return total

    return get_size(path)


# _get_volume_size():
#
# Gets the overall usage and total size of a mounted filesystem in bytes.
#
# Args:
#    path (str): The path to check
#
# Returns:
#    (int): The total number of bytes on the volume
#    (int): The number of available bytes on the volume
#
def _get_volume_size(path):
    try:
        usage = shutil.disk_usage(path)
    except OSError as e:
        raise UtilError("Failed to retrieve stats on volume for path '{}': {}".format(path, e)) from e
    return usage.total, usage.free


# _parse_size():
#
# Convert a string representing data size to a number of
# bytes. E.g. "2K" -> 2048.
#
# This uses the same format as systemd's
# [resource-control](https://www.freedesktop.org/software/systemd/man/systemd.resource-control.html#).
#
# Arguments:
#     size (str) The string to parse
#     volume (str) A path on the volume to consider for percentage
#                  specifications
#
# Returns:
#     (int|None) The number of bytes, or None if 'infinity' was specified.
#
# Raises:
#     UtilError if the string is not a valid data size.
#
def _parse_size(size, volume):
    if size == "infinity":
        return None

    matches = re.fullmatch(r"([0-9]+\.?[0-9]*)([KMGT%]?)", size)
    if matches is None:
        raise UtilError("{} is not a valid data size.".format(size))

    num, unit = matches.groups()

    if unit == "%":
        num = float(num)
        if num > 100:
            raise UtilError("{}% is not a valid percentage value.".format(num))

        disk_size, _ = _get_volume_size(volume)

        return disk_size * (num / 100)

    units = ("", "K", "M", "G", "T")
    return int(num) * 1024 ** units.index(unit)


# _pretty_size()
#
# Converts a number of bytes into a string representation in KiB, MiB, GiB, TiB
# represented as K, M, G, T etc.
#
# Args:
#   size (int): The size to convert in bytes.
#   dec_places (int): The number of decimal places to output to.
#
# Returns:
#   (str): The string representation of the number of bytes in the largest
def _pretty_size(size, dec_places=0):
    psize = size
    unit = "B"
    units = ("B", "K", "M", "G", "T")
    for unit in units:
        if psize < 1024:
            break
        if unit != units[-1]:
            psize /= 1024
    return "{size:g}{unit}".format(size=round(psize, dec_places), unit=unit)


# _is_main_process()
#
# Return whether we are in the main process or not.
#
def _is_main_process():
    assert _MAIN_PID is not None
    return os.getpid() == _MAIN_PID


# Remove a path and any empty directories leading up to it.
#
# Args:
#     basedir - The basedir at which to stop pruning even if
#               it is empty.
#     path - A path relative to basedir that should be pruned.
#
# Raises:
#     FileNotFoundError - if the path itself doesn't exist.
#     OSError - if something else goes wrong
#
def _remove_path_with_parents(basedir: Union[Path, str], path: Union[Path, str]):
    assert not os.path.isabs(path), "The path ({}) should be relative to basedir ({})".format(path, basedir)
    path = os.path.join(basedir, path)

    # Start by removing the path itself
    os.unlink(path)

    # Now walk up the directory tree and delete any empty directories
    path = os.path.dirname(path)
    while path != basedir:
        try:
            os.rmdir(path)
        except FileNotFoundError:
            # The parent directory did not exist (race conditions can
            # cause this), but it's parent directory might still be
            # ready to prune
            pass
        except OSError as e:
            if e.errno == errno.ENOTEMPTY:
                # The parent directory was not empty, so we
                # cannot prune directories beyond this point
                break
            raise

        path = os.path.dirname(path)


# Recursively remove directories, ignoring file permissions as much as
# possible.
def _force_rmtree(rootpath):
    def fix_permissions(function, path, info):
        parent = os.path.dirname(path)

        try:
            os.chmod(parent, 0o755)
        except OSError as e:
            raise UtilError("Failed to ensure write permission on directory '{}': {}".format(parent, e))

        # Directories need to be removed with `rmdir`, though
        # `os.path.isdir` will follow symlinks, so make sure it's
        # not a symlink first
        if not os.path.islink(path) and os.path.isdir(path):
            os.rmdir(path)
        else:
            os.remove(path)

    try:
        shutil.rmtree(rootpath, onerror=fix_permissions)
    except OSError as e:
        raise UtilError("Failed to remove cache directory '{}': {}".format(rootpath, e))


# Recursively make directories in target area
def _copy_directories(srcdir, destdir, target):
    this_dir = os.path.dirname(target)
    new_dir = os.path.join(destdir, this_dir)
    old_dir = os.path.join(srcdir, this_dir)

    if not os.path.lexists(new_dir):
        if this_dir:
            yield from _copy_directories(srcdir, destdir, this_dir)

        if os.path.lexists(old_dir):
            dir_stat = os.lstat(old_dir)
            mode = dir_stat.st_mode

            if stat.S_ISDIR(mode) or stat.S_ISLNK(mode):
                os.makedirs(new_dir)
                yield (new_dir, mode)
            else:
                raise UtilError("Source directory tree has file where " "directory expected: {}".format(old_dir))
    else:
        if not os.access(new_dir, os.W_OK):
            # If the destination directory is not writable, change permissions to make it
            # writable. Callers of this method (like `_process_list`) must
            # restore the original permissions towards the end of their processing.
            try:
                os.chmod(new_dir, 0o755)
                yield (new_dir, os.lstat(old_dir).st_mode)
            except PermissionError:
                raise UtilError("Directory {} is not writable".format(destdir))


# _ensure_real_directory()
#
# Ensure `path` is a real directory and there are no symlink components.
#
# Symlink components are allowed in `root`.
#
def _ensure_real_directory(root, path):
    destpath = root
    for name in os.path.split(path):
        destpath = os.path.join(destpath, name)
        try:
            deststat = os.lstat(destpath)
            if not stat.S_ISDIR(deststat.st_mode):
                relpath = destpath[len(root) :]

                if stat.S_ISLNK(deststat.st_mode):
                    filetype = "symlink"
                elif stat.S_ISREG(deststat.st_mode):
                    filetype = "regular file"
                else:
                    filetype = "special file"

                raise UtilError("Destination is a {}, not a directory: {}".format(filetype, relpath))
        except FileNotFoundError:
            os.makedirs(destpath)


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
#    actionfunc: The function to call for regular files
#    result: The FileListResult
#    filter_callback: Optional callback to invoke for every directory entry
#    ignore_missing: Dont raise any error if a source file is missing
#
#
def _process_list(
    srcdir, destdir, actionfunc, result, filter_callback=None, ignore_missing=False, report_written=False
):

    # Keep track of directory permissions, since these need to be set
    # *after* files have been written.
    permissions = []

    filelist = list_relative_paths(srcdir)

    if filter_callback:
        filelist = [path for path in filelist if filter_callback(path)]

    # Now walk the list
    for path in filelist:
        srcpath = os.path.join(srcdir, path)
        destpath = os.path.join(destdir, path)

        # Ensure that the parent of the destination path exists without symlink
        # components.
        _ensure_real_directory(destdir, os.path.dirname(path))

        # Add to the results the list of files written
        if report_written:
            result.files_written.append(path)

        # Collect overlaps
        if os.path.lexists(destpath) and not os.path.isdir(destpath):
            result.overwritten.append(path)

        # The destination directory may not have been created separately
        permissions.extend(_copy_directories(srcdir, destdir, path))

        try:
            file_stat = os.lstat(srcpath)
            mode = file_stat.st_mode

        except FileNotFoundError as e:
            # Skip this missing file
            if ignore_missing:
                continue

            raise UtilError("Source file is missing: {}".format(srcpath)) from e

        if stat.S_ISDIR(mode):
            # Ensure directory exists in destination
            _ensure_real_directory(destdir, path)
            permissions.append((destpath, os.stat(srcpath).st_mode))

        elif stat.S_ISLNK(mode):
            if not safe_remove(destpath):
                result.ignored.append(path)
                continue

            target = os.readlink(srcpath)
            os.symlink(target, destpath)

        elif stat.S_ISREG(mode):
            # Process the file.
            if not safe_remove(destpath):
                result.ignored.append(path)
                continue

            actionfunc(srcpath, destpath, result=result)

        elif stat.S_ISFIFO(mode):
            os.mkfifo(destpath, mode)

        elif stat.S_ISSOCK(mode):
            # We can't duplicate the process serving the socket anyway
            pass

        else:
            # Unsupported type.
            raise UtilError("Cannot extract {} into staging-area. Unsupported type.".format(srcpath))

    # Write directory permissions now that all files have been written
    for d, perms in permissions:
        os.chmod(d, perms)


# _set_deterministic_user()
#
# Set the uid/gid for every file in a directory tree to the process'
# euid/guid.
#
# Args:
#    directory (str): The directory to recursively set the uid/gid on
#
def _set_deterministic_user(directory):
    user = os.geteuid()
    group = os.getegid()

    for root, dirs, files in os.walk(directory.encode("utf-8"), topdown=False):
        for filename in files:
            os.chown(os.path.join(root, filename), user, group, follow_symlinks=False)

        for dirname in dirs:
            os.chown(os.path.join(root, dirname), user, group, follow_symlinks=False)


# _set_deterministic_mtime()
#
# Set the mtime for every file in a directory tree to the same.
#
# Args:
#    directory (str): The directory to recursively set the mtime on
#
def _set_deterministic_mtime(directory):
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
                os.utime(pathname, (BST_ARBITRARY_TIMESTAMP, BST_ARBITRARY_TIMESTAMP))

        os.utime(dirname, (BST_ARBITRARY_TIMESTAMP, BST_ARBITRARY_TIMESTAMP))


# _tempdir()
#
# A context manager for doing work in a temporary directory.
#
# NOTE: Unlike mkdtemp(), this method may not restrict access to other
#       users. The process umask is the only access restriction, similar
#       to mkdir().
#       This is potentially insecure. Do not create directories in /tmp
#       with this method. *Only* use this in directories whose parents are
#       more tightly controlled (i.e., non-public directories).
#
# Args:
#    dir (str): A path to a parent directory for the temporary directory
#    suffix (str): A suffix for the temproary directory name
#    prefix (str): A prefix for the temporary directory name
#
# Yields:
#    (str): The temporary directory
#
# In addition to the functionality provided by python's
# tempfile.TemporaryDirectory() context manager, this one additionally
# supports cleaning up the temp directory on SIGTERM.
#
@contextmanager
def _tempdir(*, suffix="", prefix="tmp", dir):  # pylint: disable=redefined-builtin
    # Do not allow fallback to a global temp directory. Due to the chmod
    # below, this method is not safe to be used in global temp
    # directories such as /tmp.
    assert (
        dir
    ), "Creating directories in the public fallback `/tmp` is dangerous. Please use a directory with tight access controls."

    tempdir = tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=dir)

    def cleanup_tempdir():
        if os.path.isdir(tempdir):
            _force_rmtree(tempdir)

    try:
        with _signals.terminator(cleanup_tempdir):
            # Apply mode allowed by umask
            os.chmod(tempdir, 0o777 & ~_UMASK)

            yield tempdir
    finally:
        cleanup_tempdir()


# _tempnamedfile()
#
# A context manager for doing work on an open temporary file
# which is guaranteed to be named and have an entry in the filesystem.
#
# Args:
#    mode (str): The mode in which the file is opened
#    encoding (str): The name of the encoding used to decode or encode the file
#    dir (str): A path to a parent directory for the temporary file
#    suffix (str): A suffix for the temproary file name
#    prefix (str): A prefix for the temporary file name
#
# Yields:
#    (tempfile.NamedTemporaryFile): The temporary file handle
#
# Do not use tempfile.NamedTemporaryFile() directly, as this will
# leak files on the filesystem when BuildStream exits a process
# on SIGTERM.
#
@contextmanager
def _tempnamedfile(mode="w+b", encoding=None, suffix="", prefix="tmp", dir=None):  # pylint: disable=redefined-builtin
    temp = None

    def close_tempfile():
        if temp is not None:
            temp.close()

    with _signals.terminator(close_tempfile), tempfile.NamedTemporaryFile(
        mode=mode, encoding=encoding, suffix=suffix, prefix=prefix, dir=dir
    ) as temp:
        yield temp


# _tempnamedfile_name()
#
# A context manager for doing work on a temporary file, via the filename only.
#
# Note that a Windows restriction prevents us from using both the file
# descriptor and the file name of tempfile.NamedTemporaryFile, the same file
# cannot be opened twice at the same time. This wrapper makes it easier to
# operate in a Windows-friendly way when only filenames are needed.
#
# Takes care to delete the file even if interrupted by SIGTERM. Note that there
# is a race-condition, so this is done on a best-effort basis.
#
# Args:
#    dir (str): A path to a parent directory for the temporary file, this is
#               not optional for security reasons, please see below.
#
# Note that 'dir' should not be a directory that may be shared with potential
# attackers that have rights to affect the directory, e.g. the system temp
# directory. This is because an attacker can replace the temporary file with
# e.g. a symlink to another location, that the BuildStream user has rights to
# but the attacker does not.
#
# See here for more information:
# https://www.owasp.org/index.php/Insecure_Temporary_File
#
# Yields:
#    (str): The temporary file name
#
@contextmanager
def _tempnamedfile_name(dir):  # pylint: disable=redefined-builtin
    filename = None

    def rm_tempfile():
        nonlocal filename
        if filename is not None:
            # Note that this code is re-entrant - it's possible for us to
            # "delete while we're deleting" if we are responding to SIGTERM.
            #
            # For simplicity, choose to leak the file in this unlikely case,
            # rather than introducing a scheme for handling the file sometimes
            # being missing. Note that we will still leak tempfiles on forced
            # termination anyway.
            #
            # Note that we must not try to delete the file more than once. If
            # we delete the file then another temporary file can be created
            # with the same name.
            #
            filename2 = filename
            filename = None
            os.remove(filename2)

    with _signals.terminator(rm_tempfile):
        fd, filename = tempfile.mkstemp(dir=dir)
        os.close(fd)
        try:
            yield filename
        finally:
            rm_tempfile()


# _kill_process_tree()
#
# Brutally murder a process and all of its children
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
        except psutil.NoSuchProcess:
            # It is certain that this has already been sent
            # SIGTERM, so there is a window where the process
            # could have exited already.
            pass

    # Bloody Murder
    for child in children:
        kill_proc(child)
    kill_proc(proc)


# _call()
#
# A wrapper for subprocess.call() supporting suspend and resume
#
# Args:
#    popenargs (list): Popen() arguments
#    terminate (bool): Whether to attempt graceful termination before killing
#    rest_of_args (kwargs): Remaining arguments to subprocess.call()
#
# Returns:
#    (int): The process exit code.
#    (str): The program output.
#
def _call(*popenargs, terminate=False, **kwargs):

    kwargs["start_new_session"] = True

    process = None

    old_preexec_fn = kwargs.get("preexec_fn")
    if "preexec_fn" in kwargs:
        del kwargs["preexec_fn"]

    def preexec_fn():
        os.umask(stat.S_IWGRP | stat.S_IWOTH)
        if old_preexec_fn is not None:
            old_preexec_fn()

    # Handle termination, suspend and resume
    def kill_proc():
        if process:

            # Some callers know that their subprocess can be
            # gracefully terminated, make an attempt first
            if terminate:
                proc = psutil.Process(process.pid)
                proc.terminate()

                try:
                    proc.wait(20)
                except psutil.TimeoutExpired:
                    # Did not terminate within the timeout: murder
                    _kill_process_tree(process.pid)

            else:
                # FIXME: This is a brutal but reliable approach
                #
                # Other variations I've tried which try SIGTERM first
                # and then wait for child processes to exit gracefully
                # have not reliably cleaned up process trees and have
                # left orphaned git or ssh processes alive.
                #
                # This cleans up the subprocesses reliably but may
                # cause side effects such as possibly leaving stale
                # locks behind. Hopefully this should not be an issue
                # as long as any child processes only interact with
                # the temp directories which we control and cleanup
                # ourselves.
                #
                _kill_process_tree(process.pid)

    def suspend_proc():
        if process:
            group_id = os.getpgid(process.pid)
            os.killpg(group_id, signal.SIGSTOP)

    def resume_proc():
        if process:
            group_id = os.getpgid(process.pid)
            os.killpg(group_id, signal.SIGCONT)

    with _signals.suspendable(suspend_proc, resume_proc), _signals.terminator(kill_proc):
        process = subprocess.Popen(  # pylint: disable=subprocess-popen-preexec-fn
            *popenargs, preexec_fn=preexec_fn, universal_newlines=True, **kwargs
        )
        output, _ = process.communicate()
        exit_code = process.poll()

    return (exit_code, output)


# _glob2re()
#
# Function to translate a glob style pattern into a regex
#
# Args:
#    pat (str): The glob pattern
#
# This is a modified version of the python standard library's
# fnmatch.translate() function which supports path like globbing
# a bit more correctly, and additionally supports recursive glob
# patterns with double asterisk.
#
# Note that this will only support the most basic of standard
# glob patterns, and additionally the recursive double asterisk.
#
# Support includes:
#
#   *          Match any pattern except a path separator
#   **         Match any pattern, including path separators
#   ?          Match any single character
#   [abc]      Match one of the specified characters
#   [A-Z]      Match one of the characters in the specified range
#   [!abc]     Match any single character, except the specified characters
#   [!A-Z]     Match any single character, except those in the specified range
#
def _glob2re(pat):
    i, n = 0, len(pat)
    res = "(?ms)"
    while i < n:
        c = pat[i]
        i = i + 1
        if c == "*":
            # fnmatch.translate() simply uses the '.*' separator here,
            # we only want that for double asterisk (bash 'globstar' behavior)
            #
            if i < n and pat[i] == "*":
                res = res + ".*"
                i = i + 1
            else:
                res = res + "[^/]*"
        elif c == "?":
            # fnmatch.translate() simply uses the '.' wildcard here, but
            # we dont want to match path separators here
            res = res + "[^/]"
        elif c == "[":
            j = i
            if j < n and pat[j] == "!":
                j = j + 1
            if j < n and pat[j] == "]":
                j = j + 1
            while j < n and pat[j] != "]":
                j = j + 1
            if j >= n:
                res = res + "\\["
            else:
                stuff = pat[i:j].replace("\\", "\\\\")
                i = j + 1
                if stuff[0] == "!":
                    stuff = "^" + stuff[1:]
                elif stuff[0] == "^":
                    stuff = "\\" + stuff
                res = "{}[{}]".format(res, stuff)
        else:
            res = res + re.escape(c)
    return res + r"\Z"


# _deduplicate()
#
# Remove duplicate entries in a list or other iterable.
#
# Copied verbatim from the unique_everseen() example at
# https://docs.python.org/3/library/itertools.html#itertools-recipes
#
# Args:
#    iterable (iterable): What to deduplicate
#    key (callable): Optional function to map from list entry to value
#
# Returns:
#    (generator): Generator that produces a deduplicated version of 'iterable'
#
def _deduplicate(iterable, key=None):
    seen = set()
    seen_add = seen.add
    if key is None:
        for element in itertools.filterfalse(seen.__contains__, iterable):
            seen_add(element)
            yield element
    else:
        for element in iterable:
            k = key(element)
            if k not in seen:
                seen_add(k)
                yield element


# Like os.path.getmtime(), but returns the mtime of a link rather than
# the target, if the filesystem supports that.
#
def _get_link_mtime(path):
    path_stat = os.lstat(path)
    return path_stat.st_mtime


# _message_digest()
#
# Args:
#    message_buffer (str): String to create digest of
#
# Returns:
#    (remote_execution_pb2.Digest): Content digest
#
def _message_digest(message_buffer):
    sha = hashlib.sha256(message_buffer)
    digest = remote_execution_pb2.Digest()
    digest.hash = sha.hexdigest()
    digest.size_bytes = len(message_buffer)
    return digest


# _search_upward_for_files()
#
# Searches upwards (from directory, then directory's parent directory...)
# for any of the files listed in `filenames`.
#
# If multiple filenames are specified, and present in the same directory,
# the first filename in the list will be returned.
#
# Args:
#    directory (str): The directory to begin searching for files from
#    filenames (list of str): The names of files to search for
#
# Returns:
#    (str): The directory a file was found in, or None
#    (str): The name of the first file that was found in that directory, or None
#
def _search_upward_for_files(directory, filenames):
    directory = os.path.abspath(directory)
    while True:
        for filename in filenames:
            file_path = os.path.join(directory, filename)
            if os.path.isfile(file_path):
                return directory, filename

        parent_dir = os.path.dirname(directory)
        if directory == parent_dir:
            # i.e. we've reached the root of the filesystem
            return None, None
        directory = parent_dir


# _deterministic_umask()
#
# Context managed to apply a umask to a section that may be affected by a users
# umask. Restores old mask afterwards.
#
@contextmanager
def _deterministic_umask():
    old_umask = os.umask(0o022)

    try:
        yield
    finally:
        os.umask(old_umask)


# _get_compression:
#
# Given a file name infer the compression
#
# Args:
#    tar (str): The file name from which to determine compression
#
# Returns:
#    (str): One from '', 'gz', 'xz', 'bz2'
#
# Raises:
#    UtilError: In the case where an unsupported file extension has been provided,
#               expecting compression.
#
#
def _get_compression(tar):
    mapped_extensions = {".tar": "", ".gz": "gz", ".xz": "xz", ".bz2": "bz2"}

    name, ext = os.path.splitext(tar)

    try:
        return mapped_extensions[ext]
    except KeyError:
        # If ext not in mapped_extensions, find out if inner ext is .tar
        # If so, we assume we have been given an unsupported extension,
        # which expects compression. Raise an error
        _, suffix = os.path.splitext(name)
        if suffix == ".tar":
            raise UtilError(
                "Expected compression with unknown file extension ('{}'), "
                "supported extensions are ('.tar'), ('.gz'), ('.xz'), ('.bz2')".format(ext)
            )

        # Assume just an unconventional name was provided, default to uncompressed
        return ""


# _is_single_threaded()
#
# Return whether the current Process is single-threaded. Don't count threads
# in the main process that were created by a test environment (xdist/execnet)
# before BuildStream was executed.
#
def _is_single_threaded():
    # Use psutil as threading.active_count() doesn't include gRPC threads.
    process = psutil.Process()

    if process.pid == _MAIN_PID:
        expected_num_threads = _INITIAL_NUM_THREADS_IN_MAIN_PROCESS
    else:
        expected_num_threads = 1

    # gRPC threads are not joined when shut down. Wait for them to exit.
    wait = 0.1
    for _ in range(0, int(_AWAIT_THREADS_TIMEOUT_SECONDS / wait)):
        if process.num_threads() == expected_num_threads:
            return True
        time.sleep(wait)
    return False


# _parse_version():
#
# Args:
#    version (str): The file name from which to determine compression
#
# Returns:
#    A 2-tuple of form (major version, minor version)
#
# Raises:
#    UtilError: In the case of a malformed version string
#
def _parse_version(version: str) -> Tuple[int, int]:

    try:
        versions = version.split(".")
        major = int(versions[0])
        minor = int(versions[1])
    except (IndexError, ValueError, AttributeError) as e:
        raise UtilError("Malformed version string: {}".format(version),) from e

    return major, minor


# _get_bst_api_version():
#
# Fetch the current BuildStream API version, this
# ensures that we get "2.0" for example when we are
# in a development stage leading up to 2.0.
#
# Returns:
#    A 2-tuple of form (major version, minor version)
#
def _get_bst_api_version() -> Tuple[int, int]:

    bst_major, bst_minor = get_bst_version()

    if bst_major < 2:
        bst_major = 2
        bst_minor = 0

    return (bst_major, bst_minor)
