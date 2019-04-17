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


# Return a list of files relative to the given directory
def walk_dir(root):
    for dirname, dirnames, filenames in os.walk(root):
        # ensure consistent traversal order, needed for consistent
        # handling of symlinks.
        dirnames.sort()
        filenames.sort()

        # print path to all subdirectories first.
        for subdirname in dirnames:
            yield os.path.join(dirname, subdirname)[len(root):]

        # print path to all filenames.
        for filename in filenames:
            yield os.path.join(dirname, filename)[len(root):]


# Ensure that a directory contains the given filenames.
def assert_contains(directory, expected):
    missing = set(expected)
    missing.difference_update(walk_dir(directory))
    if missing:
        raise AssertionError("Missing {} expected elements from list: {}"
                             .format(len(missing), missing))
