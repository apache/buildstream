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


#################################################
#            Implement pytest option            #
#################################################
def pytest_addoption(parser):
    parser.addoption('--integration', action='store_true', default=False,
                     help='Run integration tests')


def pytest_runtest_setup(item):
    if item.get_closest_marker('integration') and not item.config.getvalue('integration'):
        pytest.skip('skipping integration test')


#################################################
#           integration_cache fixture           #
#################################################
#
# This is yielded by the `integration_cache` fixture
#
class IntegrationCache():

    def __init__(self, cache):
        cache = os.path.abspath(cache)
        os.makedirs(cache, exist_ok=True)

        # Use the same sources every time
        self.sources = os.path.join(cache, 'sources')

        # Create a temp directory for the duration of the test for
        # the artifacts directory
        try:
            self.artifacts = tempfile.mkdtemp(dir=cache, prefix='artifacts-')
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
        shutil.rmtree(cache.artifacts)
    except FileNotFoundError:
        pass
