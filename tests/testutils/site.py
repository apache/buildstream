# Some things resolved about the execution site,
# so we dont have to repeat this everywhere
#
import os
import sys

from buildstream import utils
from buildstream._exceptions import ProgramNotFoundError

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

IS_LINUX = os.getenv('BST_FORCE_BACKEND', sys.platform).startswith('linux')

HAVE_ROOT = HAVE_BWRAP or os.geteuid() == 0
