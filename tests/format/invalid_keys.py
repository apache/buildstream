# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest
from buildstream._exceptions import ErrorDomain, LoadErrorReason
from buildstream.testing.runcli import cli  # pylint: disable=unused-import

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'invalid-keys'
)


@pytest.mark.datafiles(DATA_DIR)
def test_compositied_node_fails_usefully(cli, datafiles):
    project = str(datafiles)
    result = cli.run(project=project, args=['show', 'no-path-specified.bst'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)

    assert "synthetic node" not in result.stderr
    assert "no-path-specified.bst [line 4 column 4]: Dictionary did not contain expected key 'path'" in result.stderr
