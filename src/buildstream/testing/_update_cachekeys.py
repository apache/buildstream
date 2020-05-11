#!/usr/bin/env python3
#
#  Copyright (C) 2019 Codethink Limited
#  Copyright (C) 2020 Bloomberg Finance LP
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
# Automatically create or update the .expected files in the
# cache key test directory.
#
# Simply run without any arguments, from the directory containing the project, e.g.:
#
#   python3 -m buildstream.testing._update_cachekeys
#
# After this, add any files which were newly created and commit
# the result in order to adjust the cache key test to changed
# keys.
#
import os
import tempfile
from unittest import mock

from buildstream.testing._cachekeys import _element_filename, _parse_output_keys, _load_expected_keys
from buildstream.testing.runcli import Cli


def write_expected_key(project_dir, element_name, actual_key):
    expected_file = _element_filename(project_dir, element_name, "expected")
    with open(expected_file, "w") as f:
        f.write(actual_key)


def update_keys():
    project_dir = os.getcwd()

    with tempfile.TemporaryDirectory(dir=project_dir) as cache_dir:
        # Run bst show
        cli = Cli(cache_dir, verbose=True)
        result = cli.run(
            project=project_dir, silent=True, args=["--no-colors", "show", "--format", "%{name}::%{full-key}"],
        )

        # Load the actual keys, and the expected ones if they exist
        if not result.output:
            print("No results from parsing {}".format(project_dir))
            return

        actual_keys = _parse_output_keys(result.output)
        expected_keys = _load_expected_keys(project_dir, actual_keys, raise_error=False)

        for element_name in actual_keys:
            expected = _element_filename(project_dir, element_name, "expected")

            if actual_keys[element_name] != expected_keys[element_name]:
                if not expected_keys[element_name]:
                    print("Creating new expected file: {}".format(expected))
                else:
                    print("Updating expected file: {}".format(expected))

                write_expected_key(project_dir, element_name, actual_keys[element_name])


if __name__ == "__main__":
    #  patch the environment BST_TEST_SUITE value to something if it's not
    #  present. This avoids an exception thrown at the cli level
    bst = "BST_TEST_SUITE"
    mock_bst = os.environ.get(bst, "True")
    with mock.patch.dict(os.environ, {**os.environ, bst: mock_bst}):
        update_keys()
