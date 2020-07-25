# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import cli  # pylint: disable=unused-import

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "search")


####################################################
#                     Tests                        #
####################################################
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target",
    [
        # Search for an element in the same project which the element also depends on directly
        #
        "search-manual.bst",
        #
        # Search using a link to the manual element, where the manual element
        # is listed as a dependency (ensures that link resolution works with
        # Element.search())
        #
        "search-link.bst",
        #
        # Search for an element in a subproject which is also directly depended on
        #
        "search-subproject.bst",
        #
        # Search for a local link which links to a subproject element
        #
        "search-link-to-subproject.bst",
        #
        # Search for a link to a subproject element within that same subproject
        #
        "search-link-in-subproject.bst",
        #
        # Search for an element where the search element is in a subproject
        #
        "subproject.bst:search-target.bst",
        #
        # Search for an element via a link where the search element is in a subproject
        #
        "subproject.bst:search-link.bst",
        #
        # Search for an element in a subsubproject, where the search element is in a subproject
        #
        "subproject.bst:search-subsubproject.bst",
        #
        # Search for a link which links to a subsubproject element, within a subproject
        #
        "subproject.bst:search-link-to-subsubproject.bst",
        #
        # Search for a link to a subsubproject element within that same subsubproject, all
        # within a subproject.
        #
        "subproject.bst:search-link-in-subsubproject.bst",
        #
        # Search for an element in an overridden subproject
        #
        "subproject.bst:search-overridden-subsubproject.bst",
        #
        # Search for a link which links to an overridden subsubproject element
        #
        "subproject.bst:search-link-to-overridden-subsubproject.bst",
        #
        # Search for a link to a subsubproject element within an overridden subsubproject.
        #
        "subproject.bst:search-link-in-overridden-subsubproject.bst",
    ],
)
def test_search(cli, datafiles, target):
    project = str(datafiles)

    result = cli.run(project=project, args=["show", target])
    result.assert_success()
