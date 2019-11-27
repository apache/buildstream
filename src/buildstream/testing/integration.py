#
#  Copyright (C) 2017 Codethink Limited
#  Copyright (C) 2018 Bloomberg Finance LP
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
"""
Integration - tools for inspecting the output of plugin integration tests
=========================================================================

This module contains utilities for inspecting the artifacts produced during
integration tests.
"""

import os
import shutil
import tempfile

import pytest

from buildstream import utils


# Return a list of files relative to the given directory
def walk_dir(root):
    for dirname, dirnames, filenames in os.walk(root):
        # ensure consistent traversal order, needed for consistent
        # handling of symlinks.
        dirnames.sort()
        filenames.sort()

        # print path to all subdirectories first.
        for subdirname in dirnames:
            yield os.path.join(dirname, subdirname)[len(root) :]

        # print path to all filenames.
        for filename in filenames:
            yield os.path.join(dirname, filename)[len(root) :]


# Ensure that a directory contains the given filenames.
# If `strict` is `True` then no additional filenames are allowed.
def assert_contains(directory, expected, strict=False):
    expected = set(expected)
    missing = set(expected)
    found = set(walk_dir(directory))

    # elements expected but not found
    missing.difference_update(found)

    if missing:
        msg = "Missing {} expected elements from list: {}".format(len(missing), missing)
        raise AssertionError(msg)

    if strict:
        # elements found but not expected
        found.difference_update(expected)
        msg = "{} additional elements were present in the directory: {}".format(len(found), found)
        if found:
            raise AssertionError(msg)


class IntegrationCache:
    def __init__(self, cache):
        self.root = os.path.abspath(cache)
        os.makedirs(cache, exist_ok=True)

        # Use the same sources every time
        self.sources = os.path.join(self.root, "sources")

        # Create a temp directory for the duration of the test for
        # the artifacts directory
        try:
            self.cachedir = tempfile.mkdtemp(dir=self.root, prefix="cache-")
            # Apply mode allowed by umask
            os.chmod(self.cachedir, 0o777 & ~utils.get_umask())
        except OSError as e:
            raise AssertionError("Unable to create test directory !") from e


@pytest.fixture(scope="session")
def integration_cache(request):
    # Set the cache dir to the INTEGRATION_CACHE variable, or the
    # default if that is not set.
    if "INTEGRATION_CACHE" in os.environ:
        cache_dir = os.environ["INTEGRATION_CACHE"]
    else:
        cache_dir = os.path.abspath("./integration-cache")

    cache = IntegrationCache(cache_dir)

    yield cache

    # Clean up the artifacts after each test session - we only want to
    # cache sources between tests
    try:
        shutil.rmtree(cache.cachedir)
    except FileNotFoundError:
        pass
    try:
        shutil.rmtree(os.path.join(cache.root, "cas"))
    except FileNotFoundError:
        pass
