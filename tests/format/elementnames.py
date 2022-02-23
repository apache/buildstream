# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream._testing import cli  # pylint: disable=unused-import

DATA_DIR = os.path.dirname(os.path.realpath(__file__))


@pytest.mark.parametrize(
    "target,domain,reason,provenance",
    [
        # When specifying a bad suffix on the command line we get a different error, we
        # catch this error earlier on in the load sequence while sorting out element and
        # artifact names and glob expressions.
        #
        ("farm.pony", ErrorDomain.STREAM, "invalid-element-names", None),
        ('The "quoted" pony.bst', ErrorDomain.LOAD, LoadErrorReason.BAD_CHARACTERS_IN_NAME, None),
        (
            "bad-suffix-dep.bst",
            ErrorDomain.LOAD,
            LoadErrorReason.BAD_ELEMENT_SUFFIX,
            "bad-suffix-dep.bst [line 3 column 2]",
        ),
        (
            "bad-chars-dep.bst",
            ErrorDomain.LOAD,
            LoadErrorReason.BAD_CHARACTERS_IN_NAME,
            "bad-chars-dep.bst [line 3 column 2]",
        ),
    ],
    ids=["toplevel-bad-suffix", "toplevel-bad-chars", "dependency-bad-suffix", "dependency-bad-chars"],
)
@pytest.mark.datafiles(DATA_DIR)
def test_invalid_element_names(cli, datafiles, target, domain, reason, provenance):
    project = os.path.join(str(datafiles), "elementnames")
    result = cli.run(project=project, silent=True, args=["show", target])
    result.assert_main_error(domain, reason)
    if provenance:
        assert provenance in result.stderr
