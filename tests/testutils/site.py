# Some things resolved about the execution site,
# so we dont have to repeat this everywhere
#
import os
import sys
import platform

from buildstream import utils, ProgramNotFoundError


try:
    OSTREE_CLI = utils.get_host_tool('ostree')
    HAVE_OSTREE_CLI = True
except ProgramNotFoundError:
    HAVE_OSTREE_CLI = False

try:
    from bst_plugins_experimental.sources import _ostree  # pylint: disable=unused-import
    HAVE_OSTREE = True
except (ImportError, ValueError):
    HAVE_OSTREE = False

IS_LINUX = os.getenv('BST_FORCE_BACKEND', sys.platform).startswith('linux')
IS_WSL = (IS_LINUX and 'Microsoft' in platform.uname().release)
IS_WINDOWS = (os.name == 'nt')
