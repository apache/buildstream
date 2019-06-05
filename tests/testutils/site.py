# Some things resolved about the execution site,
# so we dont have to repeat this everywhere
#

try:
    from bst_plugins_experimental.sources import _ostree  # pylint: disable=unused-import
    HAVE_OSTREE = True
except (ImportError, ValueError):
    HAVE_OSTREE = False
