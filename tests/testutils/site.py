# Some things resolved about the execution site,
# so we dont have to repeat this everywhere
#

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
