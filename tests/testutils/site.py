# Some things resolved about the execution site,
# so we dont have to repeat this everywhere
#
import os
import sys
import platform

from buildstream import _site, utils, ProgramNotFoundError
from buildstream._platform import Platform


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

try:
    utils.get_host_tool('bwrap')
    HAVE_BWRAP = True
    HAVE_BWRAP_JSON_STATUS = _site.get_bwrap_version() >= (0, 3, 2)
except ProgramNotFoundError:
    HAVE_BWRAP = False
    HAVE_BWRAP_JSON_STATUS = False

try:
    utils.get_host_tool('lzip')
    HAVE_LZIP = True
except ProgramNotFoundError:
    HAVE_LZIP = False

try:
    import arpy  # pylint: disable=unused-import
    HAVE_ARPY = True
except ImportError:
    HAVE_ARPY = False

IS_LINUX = os.getenv('BST_FORCE_BACKEND', sys.platform).startswith('linux')
IS_WSL = (IS_LINUX and 'Microsoft' in platform.uname().release)
IS_WINDOWS = (os.name == 'nt')

if not IS_LINUX:
    HAVE_SANDBOX = True   # fallback to a chroot sandbox on unix
elif IS_WSL:
    HAVE_SANDBOX = False  # Sandboxes are inoperable under WSL due to lack of FUSE
elif IS_LINUX and HAVE_BWRAP:
    HAVE_SANDBOX = True
else:
    HAVE_SANDBOX = False

MACHINE_ARCH = Platform.get_host_arch()
