# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.exceptions import ErrorDomain
from buildstream._testing import cli  # pylint: disable=unused-import

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "stack")


#
# Assert that we have errors when trying to have runtime-only or
# build-only dependencies.
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target",
    [
        "build-only-stack.bst",
        "runtime-only-stack.bst",
    ],
)
def test_require_build_and_run(cli, datafiles, target):
    project = str(datafiles)
    result = cli.run(project=project, args=["show", target])
    result.assert_main_error(ErrorDomain.ELEMENT, "stack-requires-build-and-run")
