# Some things resolved about the execution site,
# so we dont have to repeat this everywhere
#
import os
import sys
import platform

from buildstream import utils, ProgramNotFoundError
from buildstream.testing._utils.site import HAVE_BWRAP as _HAVE_BWRAP


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

if not IS_LINUX:
    HAVE_SANDBOX = True   # fallback to a chroot sandbox on unix
elif IS_WSL:
    HAVE_SANDBOX = False  # Sandboxes are inoperable under WSL due to lack of FUSE
elif IS_LINUX and _HAVE_BWRAP:
    HAVE_SANDBOX = True
else:
    HAVE_SANDBOX = False
