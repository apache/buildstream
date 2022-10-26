#!/usr/bin/env python3
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
#  Authors:
#        Tristan Maat <tristan.maat@codethink.co.uk>
#
import os

import pkg_resources
import pytest

from buildstream._testing import register_repo_kind, sourcetests_collection_hook
from buildstream._testing._fixtures import (  # pylint: disable=unused-import
    default_thread_number,
    thread_check,
)
from buildstream._testing.integration import integration_cache  # pylint: disable=unused-import

from tests.testutils.repo.tar import Tar


#
# This file is loaded by pytest, we use it to add a custom
# `--integration` option to our test suite, and to install
# a session scope fixture.
#


#################################################
#            Implement pytest option            #
#################################################
def pytest_addoption(parser):
    parser.addoption("--integration", action="store_true", default=False, help="Run integration tests")
    parser.addoption("--plugins", action="store_true", default=False, help="Run only plugins tests")
    parser.addoption("--remote-execution", action="store_true", default=False, help="Run remote-execution tests only")
    parser.addoption("--remote-cache", action="store_true", default=False, help="Run remote-cache tests only")


def pytest_runtest_setup(item):
    # Without --integration: skip tests not marked with 'integration'
    if not item.config.getvalue("integration"):
        if item.get_closest_marker("integration"):
            pytest.skip("skipping integration test")

    # With --remote-execution: only run tests marked with 'remoteexecution'
    if item.config.getvalue("remote_execution"):
        if not item.get_closest_marker("remoteexecution"):
            pytest.skip("skipping non remote-execution test")

    # Without --remote-execution: skip tests marked with 'remoteexecution'
    else:
        if item.get_closest_marker("remoteexecution"):
            pytest.skip("skipping remote-execution test")

    # With --remote-cache: only run tests marked with 'remotecache'
    if item.config.getvalue("remote_cache"):
        if not item.get_closest_marker("remotecache"):
            pytest.skip("skipping non remote-cache test")

    # Without --remote-cache: skip tests marked with 'remotecache'
    else:
        if item.get_closest_marker("remotecache"):
            pytest.skip("skipping remote-cache test")

    # With --plugins only run plugins tests
    if item.config.getvalue("plugins"):
        if not item.get_closest_marker("generic_source_test"):
            pytest.skip("Skipping not generic source test")


#################################################
#           remote_services fixture             #
#################################################
#
# This is returned by the `remote_services` fixture
#
class RemoteServices:
    def __init__(self, **kwargs):
        self.action_service = kwargs.get("action_service")
        self.artifact_service = kwargs.get("artifact_service")
        self.exec_service = kwargs.get("exec_service")
        self.source_service = kwargs.get("source_service")
        self.storage_service = kwargs.get("storage_service")
        self.artifact_index_service = kwargs.get("artifact_index_service")
        self.artifact_storage_service = kwargs.get("artifact_storage_service")


@pytest.fixture(scope="session")
def remote_services(request):
    kwargs = {}
    # Look for remote services configuration in environment.
    if "ARTIFACT_CACHE_SERVICE" in os.environ:
        kwargs["artifact_service"] = os.environ.get("ARTIFACT_CACHE_SERVICE")

    if "ARTIFACT_INDEX_SERVICE" in os.environ:
        kwargs["artifact_index_service"] = os.environ.get("ARTIFACT_INDEX_SERVICE")

    if "ARTIFACT_STORAGE_SERVICE" in os.environ:
        kwargs["artifact_storage_service"] = os.environ.get("ARTIFACT_STORAGE_SERVICE")

    if "REMOTE_EXECUTION_SERVICE" in os.environ:
        kwargs["action_service"] = os.environ.get("REMOTE_EXECUTION_SERVICE")
        kwargs["exec_service"] = os.environ.get("REMOTE_EXECUTION_SERVICE")
        kwargs["storage_service"] = os.environ.get("REMOTE_EXECUTION_SERVICE")

    if "SOURCE_CACHE_SERVICE" in os.environ:
        kwargs["source_service"] = os.environ.get("SOURCE_CACHE_SERVICE")

    return RemoteServices(**kwargs)


#################################################
# Setup for templated source tests              #
#################################################
register_repo_kind("tar", Tar, None)


# This hook enables pytest to collect the templated source tests from
# buildstream._testing
def pytest_sessionstart(session):
    if session.config.getvalue("plugins"):
        # Enable all plugins that implement the 'buildstream.tests.source_plugins' hook
        for entrypoint in pkg_resources.iter_entry_points("buildstream.tests.source_plugins"):
            module = entrypoint.load()
            module.register_sources()

    sourcetests_collection_hook(session)


#################################################
#             Isolated environment              #
#################################################
@pytest.fixture(scope="session", autouse=True)
def set_xdg_paths(pytestconfig):
    for env_var, default in [
        ("HOME", "tmp"),
        ("XDG_CACHE_HOME", "tmp/cache"),
        ("XDG_CONFIG_HOME", "tmp/config"),
        ("XDG_DATA_HOME", "tmp/share"),
    ]:
        value = os.environ.get("BST_TEST_{}".format(env_var))
        if value is None:
            value = os.path.realpath(os.path.join(pytestconfig.getoption("basetemp"), default))

        os.environ[env_var] = value
