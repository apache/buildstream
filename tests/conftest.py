#!/usr/bin/env python3
#
#  Copyright (C) 2018 Codethink Limited
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
