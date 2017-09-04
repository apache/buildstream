# Some things resolved about the execution site,
# so we dont have to repeat this everywhere
#
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
