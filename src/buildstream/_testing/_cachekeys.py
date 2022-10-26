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

import os
from collections import OrderedDict

from .runcli import Cli


def check_cache_key_stability(project_path: os.PathLike, cli: Cli) -> None:
    """
    Check that the cache key of various elements has not changed.

    This ensures that elements do not break cache keys unexpectedly.

    The format of the project is expected to be:

    .. code-block::

        ./
        ./project.conf
        ./elem1.bst
        ./elem1.expected
        ./elem2.bst
        ./elem2.expected
        # Or in sub-directories
        ./mydir/elem3.bst
        ./mydir/elem3.expected

    The ``.expected`` file should contain the expected cache key.

    In order to automatically created the ``.expected`` files, or updated them,
    you can run ``python3 -m buildstream._testing._update_cachekeys`` in the
    project's directory.

    :param project_path: Path to a project
    :param cli: a `cli` object as provided by the fixture :func:`buildstream._testing.runcli.cli`
    """
    result = cli.run(
        project=project_path, silent=True, args=["show", "--format", "%{name}::%{full-key}", "target.bst"]
    )
    result.assert_success()
    _assert_cache_keys(project_path, result.output)


###############################
## Internal Helper functions ##
###############################
# Those functions are for internal use only and are not part of the public API


def _element_filename(project_dir, element_name, alt_suffix=None):
    # Get whole filename in the temp project with
    # the option of changing the .bst suffix to something else
    #
    if alt_suffix:

        # Just in case...
        assert element_name.endswith(".bst")

        # Chop off the 'bst' in '.bst' and add the new suffix
        element_name = element_name[:-3]
        element_name = element_name + alt_suffix

    return os.path.join(project_dir, element_name)


def _parse_output_keys(output):
    # Returns an OrderedDict of element names
    # and their cache keys
    #
    actual_keys = OrderedDict()
    lines = output.splitlines()
    for line in lines:
        split = line.split("::")
        name = split[0]
        key = split[1]
        actual_keys[name] = key

    return actual_keys


def _load_expected_keys(project_dir, actual_keys, raise_error=True):
    # Returns an OrderedDict of element names
    # and their cache keys
    #
    expected_keys = OrderedDict()
    for element_name in actual_keys:
        expected = _element_filename(project_dir, element_name, "expected")
        try:
            with open(expected, "r", encoding="utf-8") as f:
                expected_key = f.read()
                expected_key = expected_key.strip()
        except FileNotFoundError:
            expected_key = None
            if raise_error:
                raise Exception(
                    "Cache key test needs update, "
                    + "expected file {} not found.\n\n".format(expected)
                    + "Use python3 -m buildstream._testing._update_cachekeys in the"
                    + " project's directory to automatically update this test case"
                )

        expected_keys[element_name] = expected_key

    return expected_keys


def _assert_cache_keys(project_dir, output):
    # Read in the expected keys from the cache key test directory
    # and parse the actual keys from the `bst show` output
    #
    actual_keys = _parse_output_keys(output)
    expected_keys = _load_expected_keys(project_dir, actual_keys)
    mismatches = []

    for element_name in actual_keys:
        if actual_keys[element_name] != expected_keys[element_name]:
            mismatches.append(element_name)

    if mismatches:
        info = ""
        for element_name in mismatches:
            info += (
                "  Element: {}\n".format(element_name)
                + "    Expected: {}\n".format(expected_keys[element_name])
                + "    Actual: {}\n".format(actual_keys[element_name])
            )

        raise AssertionError(
            "Cache key mismatches occurred:\n{}\n".format(info)
            + "Use python3 -m buildstream._testing._update_cachekeys in the project's "
            + "directory to automatically update this test case"
        )
