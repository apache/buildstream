# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os

import pytest

from buildstream import _yaml
from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream.testing.runcli import cli  # pylint: disable=unused-import

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "remote-exec-config")

# Tests that we get a useful error message when supplying invalid
# remote execution configurations.


# Assert that if both 'url' (the old style) and 'execution-service' (the new style)
# are used at once, a LoadError results.
@pytest.mark.datafiles(DATA_DIR)
def test_old_and_new_configs(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "missing-certs")

    project_conf = {
        "name": "test",
        "remote-execution": {
            "url": "https://cache.example.com:12345",
            "execution-service": {"url": "http://localhost:8088"},
            "storage-service": {"url": "http://charactron:11001",},
        },
    }
    project_conf_file = os.path.join(project, "project.conf")
    _yaml.roundtrip_dump(project_conf, project_conf_file)

    # Use `pull` here to ensure we try to initialize the remotes, triggering the error
    #
    # This does not happen for a simple `bst show`.
    result = cli.run(project=project, args=["artifact", "pull", "element.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA, "specify one")


# Assert that if either the client key or client cert is specified
# without specifying its counterpart, we get a comprehensive LoadError
# instead of an unhandled exception.
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("config_key, config_value", [("client-cert", "client.crt"), ("client-key", "client.key")])
def test_missing_certs(cli, datafiles, config_key, config_value):
    project = os.path.join(datafiles.dirname, datafiles.basename, "missing-certs")

    project_conf = {
        "name": "test",
        "remote-execution": {
            "execution-service": {"url": "http://localhost:8088"},
            "storage-service": {"url": "http://charactron:11001", config_key: config_value,},
        },
    }
    project_conf_file = os.path.join(project, "project.conf")
    _yaml.roundtrip_dump(project_conf, project_conf_file)

    # Use `pull` here to ensure we try to initialize the remotes, triggering the error
    #
    # This does not happen for a simple `bst show`.
    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA, "Your config is missing")


# Assert that if incomplete information is supplied we get a sensible error message.
@pytest.mark.datafiles(DATA_DIR)
def test_empty_config(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "missing-certs")

    project_conf = {"name": "test", "remote-execution": {}}
    project_conf_file = os.path.join(project, "project.conf")
    _yaml.roundtrip_dump(project_conf, project_conf_file)

    # Use `pull` here to ensure we try to initialize the remotes, triggering the error
    #
    # This does not happen for a simple `bst show`.
    result = cli.run(project=project, args=["artifact", "pull", "element.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA, "specify one")
