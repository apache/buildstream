# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os

import pytest

from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream.testing.runcli import cli  # pylint: disable=unused-import

# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


@pytest.mark.datafiles(DATA_DIR)
def test_ensure_misformed_project_overrides_give_sensible_errors(cli, datafiles):
    userconfig = {"projects": {"test": []}}
    cli.configure(userconfig)

    result = cli.run(project=datafiles, args=["show"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)
