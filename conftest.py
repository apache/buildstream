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

import os
import shutil

import pytest


def pytest_addoption(parser):
    parser.addoption('--integration', action='store_true', default=False,
                     help='Run integration tests')


def pytest_runtest_setup(item):
    if item.get_marker('integration') and not item.config.getvalue('integration'):
        pytest.skip('skipping integration test')


@pytest.fixture(scope='session')
def integration_cache(request):

    # Set the tempdir to the INTEGRATION_CACHE variable, or the
    # default if that is not set.
    if 'INTEGRATION_CACHE' in os.environ:
        cache_dir = os.environ['INTEGRATION_CACHE']
    else:
        cache_dir = os.path.abspath('./integration-cache')

    yield cache_dir

    # Clean up the artifacts after each test run - we only want to
    # cache sources
    try:
        shutil.rmtree(os.path.join(cache_dir, 'artifacts'))
    except FileNotFoundError:
        pass
