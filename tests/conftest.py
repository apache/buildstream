#!/usr/bin/env python3
#
#  Copyright (C) 2018 Codethink Limited
#  Copyright (C) 2019 Bloomberg Finance LLP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#        Tristan Maat <tristan.maat@codethink.co.uk>
#
import os
import shutil
import tempfile
import pytest
from buildstream._platform.platform import Platform
from buildstream.plugintestutils import register_repo_kind, sourcetests_collection_hook

from tests.testutils.repo.git import Git
from tests.testutils.repo.bzr import Bzr
from tests.testutils.repo.ostree import OSTree
from tests.testutils.repo.tar import Tar
from tests.testutils.repo.zip import Zip


#
# This file is loaded by pytest, we use it to add a custom
# `--integration` option to our test suite, and to install
# a session scope fixture.
#


#################################################
#            Implement pytest option            #
#################################################
def pytest_addoption(parser):
    parser.addoption('--integration', action='store_true', default=False,
                     help='Run integration tests')

    parser.addoption('--remote-execution', action='store_true', default=False,
                     help='Run remote-execution tests only')


def pytest_runtest_setup(item):
    # Without --integration: skip tests not marked with 'integration'
    if not item.config.getvalue('integration'):
        if item.get_closest_marker('integration'):
            pytest.skip('skipping integration test')

    # With --remote-execution: only run tests marked with 'remoteexecution'
    if item.config.getvalue('remote_execution'):
        if not item.get_closest_marker('remoteexecution'):
            pytest.skip('skipping non remote-execution test')

    # Without --remote-execution: skip tests marked with 'remoteexecution'
    else:
        if item.get_closest_marker('remoteexecution'):
            pytest.skip('skipping remote-execution test')


#################################################
#           integration_cache fixture           #
#################################################
#
# This is yielded by the `integration_cache` fixture
#
class IntegrationCache():

    def __init__(self, cache):
        self.root = os.path.abspath(cache)
        os.makedirs(cache, exist_ok=True)

        # Use the same sources every time
        self.sources = os.path.join(self.root, 'sources')

        # Create a temp directory for the duration of the test for
        # the artifacts directory
        try:
            self.cachedir = tempfile.mkdtemp(dir=self.root, prefix='cache-')
        except OSError as e:
            raise AssertionError("Unable to create test directory !") from e


@pytest.fixture(scope='session')
def integration_cache(request):
    # Set the cache dir to the INTEGRATION_CACHE variable, or the
    # default if that is not set.
    if 'INTEGRATION_CACHE' in os.environ:
        cache_dir = os.environ['INTEGRATION_CACHE']
    else:
        cache_dir = os.path.abspath('./integration-cache')

    cache = IntegrationCache(cache_dir)

    yield cache

    # Clean up the artifacts after each test run - we only want to
    # cache sources between runs
    try:
        shutil.rmtree(cache.cachedir)
    except FileNotFoundError:
        pass
    try:
        shutil.rmtree(os.path.join(cache.root, 'cas'))
    except FileNotFoundError:
        pass


#################################################
#           remote_services fixture             #
#################################################
#
# This is returned by the `remote_services` fixture
#
class RemoteServices():

    def __init__(self, **kwargs):
        self.action_service = kwargs.get('action_service')
        self.artifact_service = kwargs.get('artifact_service')
        self.exec_service = kwargs.get('exec_service')
        self.source_service = kwargs.get('source_service')
        self.storage_service = kwargs.get('storage_service')


@pytest.fixture(scope='session')
def remote_services(request):
    kwargs = {}
    # Look for remote services configuration in environment.
    if 'ARTIFACT_CACHE_SERVICE' in os.environ:
        kwargs['artifact_service'] = os.environ.get('ARTIFACT_CACHE_SERVICE')

    if 'REMOTE_EXECUTION_SERVICE' in os.environ:
        kwargs['action_service'] = os.environ.get('REMOTE_EXECUTION_SERVICE')
        kwargs['exec_service'] = os.environ.get('REMOTE_EXECUTION_SERVICE')
        kwargs['storage_service'] = os.environ.get('REMOTE_EXECUTION_SERVICE')

    if 'SOURCE_CACHE_SERVICE' in os.environ:
        kwargs['source_service'] = os.environ.get('SOURCE_CACHE_SERVICE')

    return RemoteServices(**kwargs)


#################################################
#         Automatically reset the platform      #
#################################################
#
# This might need some refactor, maybe buildstream
# needs to cleanup more gracefully and we could remove this.
#
def clean_platform_cache():
    Platform._instance = None


@pytest.fixture(autouse=True)
def ensure_platform_cache_is_clean():
    clean_platform_cache()


#################################################
# Setup for templated source tests              #
#################################################
register_repo_kind('git', Git)
register_repo_kind('bzr', Bzr)
register_repo_kind('ostree', OSTree)
register_repo_kind('tar', Tar)
register_repo_kind('zip', Zip)


# This hook enables pytest to collect the templated source tests from
# buildstream.plugintestutils
def pytest_sessionstart(session):
    sourcetests_collection_hook(session)
