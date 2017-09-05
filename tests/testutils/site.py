# Some things resolved about the execution site,
# so we dont have to repeat this everywhere
#
import os

from buildstream import exceptions, utils

try:
    utils.get_host_tool('bzr')
    HAVE_BZR = True
except exceptions.ProgramNotFoundError:
    HAVE_BZR = False

try:
    utils.get_host_tool('git')
    HAVE_GIT = True
except exceptions.ProgramNotFoundError:
    HAVE_GIT = False

try:
    utils.get_host_tool('ostree')
    HAVE_OSTREE_CLI = True
except exceptions.ProgramNotFoundError:
    HAVE_OSTREE_CLI = False

try:
    from buildstream import _ostree
    HAVE_OSTREE = True
except ImportError:
    HAVE_OSTREE = False

try:
    utils.get_host_tool('bwrap')
    HAVE_BWRAP = True
except exceptions.ProgramNotFoundError:
    HAVE_BWRAP = False

HAVE_ROOT = HAVE_BWRAP or os.geteuid() == 0
