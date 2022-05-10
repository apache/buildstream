# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os

import pytest

from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream._testing.runcli import cli  # pylint: disable=unused-import

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "remote-exec-config")


# Assert that if either the client key or client cert is specified
# without specifying its counterpart, we get a comprehensive LoadError
# instead of an unhandled exception.
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("config_key, config_value", [("client-cert", "client.crt"), ("client-key", "client.key")])
def test_missing_certs(cli, datafiles, config_key, config_value):
    project = os.path.join(datafiles.dirname, datafiles.basename, "missing-certs")

    cli.configure(
        {
            "remote-execution": {
                "execution-service": {"url": "http://localhost:8088"},
                "storage-service": {
                    "url": "http://charactron:11001",
                    config_key: config_value,
                },
            },
        }
    )

    # Use `pull` here to ensure we try to initialize the remotes, triggering the error
    #
    # This does not happen for a simple `bst show`.
    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA, "Your config is missing")
