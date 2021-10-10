# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream.testing import cli  # pylint: disable=unused-import

DATA_DIR = os.path.dirname(os.path.realpath(__file__))


@pytest.mark.parametrize(
    "target,reason,provenance",
    [
        ("farm.pony", LoadErrorReason.BAD_ELEMENT_SUFFIX, None),
        ('The "quoted" pony.bst', LoadErrorReason.BAD_CHARACTERS_IN_NAME, None),
        ("bad-suffix-dep.bst", LoadErrorReason.BAD_ELEMENT_SUFFIX, "bad-suffix-dep.bst [line 3 column 2]"),
        ("bad-chars-dep.bst", LoadErrorReason.BAD_CHARACTERS_IN_NAME, "bad-chars-dep.bst [line 3 column 2]"),
    ],
    ids=["toplevel-bad-suffix", "toplevel-bad-chars", "dependency-bad-suffix", "dependency-bad-chars"],
)
@pytest.mark.datafiles(DATA_DIR)
def test_invalid_element_names(cli, datafiles, target, reason, provenance):
    project = os.path.join(str(datafiles), "elementnames")
    result = cli.run(project=project, silent=True, args=["show", target])
    result.assert_main_error(ErrorDomain.LOAD, reason)
    if provenance:
        assert provenance in result.stderr
