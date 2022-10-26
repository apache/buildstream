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

from ._cachekeys import _element_filename, _parse_output_keys, _load_expected_keys
from .runcli import Cli


def write_expected_key(project_dir, element_name, actual_key):
    expected_file = _element_filename(project_dir, element_name, "expected")
    with open(expected_file, "w", encoding="utf-8") as f:
        f.write(actual_key)


def update_keys():
    project_dir = os.getcwd()

    with tempfile.TemporaryDirectory(dir=project_dir) as cache_dir:
        directory = os.path.join(str(cache_dir), "cache")

        # Run bst show
        cli = Cli(directory, verbose=True)
        result = cli.run(
            project=project_dir,
            silent=True,
            args=["--no-colors", "show", "--format", "%{name}::%{full-key}"],
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
