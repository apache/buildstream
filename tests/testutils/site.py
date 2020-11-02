# Some things resolved about the execution site,
# so we dont have to repeat this everywhere
#
import os
import sys
import tempfile

from buildstream import utils, ProgramNotFoundError

try:
    utils.get_host_tool('bzr')
    HAVE_BZR = True
except ProgramNotFoundError:
    HAVE_BZR = False

try:
    utils.get_host_tool('git')
    HAVE_GIT = True
except ProgramNotFoundError:
    HAVE_GIT = False

try:
    utils.get_host_tool('ostree')
    HAVE_OSTREE_CLI = True
except ProgramNotFoundError:
    HAVE_OSTREE_CLI = False

try:
    from buildstream import _ostree
    HAVE_OSTREE = True
except (ImportError, ValueError):
    HAVE_OSTREE = False

try:
    utils.get_host_tool('bwrap')
    HAVE_BWRAP = True
except ProgramNotFoundError:
    HAVE_BWRAP = False

try:
    utils.get_host_tool('lzip')
    HAVE_LZIP = True
except ProgramNotFoundError:
    HAVE_LZIP = False

try:
    import arpy
    HAVE_ARPY = True
except ImportError:
    HAVE_ARPY = False

IS_LINUX = os.getenv('BST_FORCE_BACKEND', sys.platform).startswith('linux')


# Check if we have subsecond mtime support on the
# filesystem where @directory is located.
#
def have_subsecond_mtime(directory):

    try:
        test_file, test_filename = tempfile.mkstemp(dir=directory)
        os.close(test_file)
    except OSError:
        # If we can't create a temp file, lets just say this is False
        return False

    try:
        os.utime(test_filename, times=None, ns=(int(12345), int(12345)))
    except OSError:
        # If we can't set the mtime, lets just say this is False
        os.unlink(test_filename)
        return False

    try:
        stat_result = os.stat(test_filename)
    except OSError:
        # If we can't stat the file, lets just say this is False
        os.unlink(test_filename)
        return False

    os.unlink(test_filename)

    return stat_result.st_mtime_ns == 12345
