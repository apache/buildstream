# Some things resolved about the execution site,
# so we dont have to repeat this everywhere
#
import os
import subprocess
import sys

from buildstream import _site, utils, ProgramNotFoundError
from buildstream._platform import Platform

try:
    utils.get_host_tool('bzr')
    HAVE_BZR = True
except ProgramNotFoundError:
    HAVE_BZR = False

try:
    utils.get_host_tool('git')
    HAVE_GIT = True
    out = str(subprocess.check_output(['git', '--version']), "utf-8")
    version = tuple(int(x) for x in out.split(' ')[2].split('.'))
    HAVE_OLD_GIT = version < (1, 8, 5)
except ProgramNotFoundError:
    HAVE_GIT = False
    HAVE_OLD_GIT = False

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
    import arpy
    HAVE_ARPY = True
except ImportError:
    HAVE_ARPY = False

IS_LINUX = os.getenv('BST_FORCE_BACKEND', sys.platform).startswith('linux')
IS_WINDOWS = (os.name == 'nt')

MACHINE_ARCH = Platform.get_host_arch()
