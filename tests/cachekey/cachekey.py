# Cache Key Test Instructions
#
# Adding Tests
# ~~~~~~~~~~~~
# Cache key tests are bst element files created created in such a way
# to exercise a feature which would cause the cache key for an element
# or source to be calculated differently.
#
# Adding tests is a matter to adding files to the project found in the
# 'project' subdirectory of this test case. Any files should be depended
# on by the main `target.bst` in the toplevel of the project.
#
# One test is comprised of one `<element-name>.bst` file and one
# '<element-name>.expected' file in the same directory, containing the
# expected cache key.
#
# Running the cache key test once will reveal what the new element's
# cache key should be and will also cause the depending elements to
# change cache keys.
#
#
# Updating tests
# ~~~~~~~~~~~~~~
# When a test fails it will come with a summary of which cache keys
# in the test project have mismatched.
#
# Also, in the case that the tests have changed or the artifact
# versions have changed in some way and the test needs to be
# updated; the expected cache keys for the given run are dumped to
# '<element-name>.actual' files beside the corresponding
# '<element-name>.expected' files they mismatched with, all inside
# a temporary test directory.
#
# One can now easily copy over the .actual files from a failed
# run over to the corresponding .expected source files and commit
# the result.
#
from tests.testutils.runcli import cli

import os
from collections import OrderedDict
import pytest


##############################################
#                Some Helpers                #
##############################################

# Get whole filename in the temp project with
# the option of changing the .bst suffix to something else
#
def element_filename(project_dir, element_name, alt_suffix=None):

    if alt_suffix:

        # Just in case...
        assert(element_name.endswith('.bst'))

        # Chop off the 'bst' in '.bst' and add the new suffix
        element_name = element_name[:-3]
        element_name = element_name + alt_suffix

    return os.path.join(project_dir, element_name)


# Returns an OrderedDict of element names
# and their cache keys
#
def parse_output_keys(output):
    actual_keys = OrderedDict()
    lines = output.splitlines()
    for line in lines:
        split = line.split("::")
        name = split[0]
        key = split[1]
        actual_keys[name] = key

    return actual_keys


# Returns an OrderedDict of element names
# and their cache keys
#
def load_expected_keys(project_dir, actual_keys):

    expected_keys = OrderedDict()
    for element_name in actual_keys:
        expected = element_filename(project_dir, element_name, 'expected')
        try:
            with open(expected, 'r') as f:
                expected_key = f.read()
                expected_key = expected_key.strip()
        except FileNotFoundError as e:
            raise Exception("Cache key test needs update, " +
                            "expected file {} not found.\n".format(expected) +
                            "Hint: Actual key for element {} is: {}".format(
                                element_name,
                                actual_keys[element_name]))

        expected_keys[element_name] = expected_key

    return expected_keys


def assert_cache_keys(project_dir, output):

    # Read in the expected keys from the cache key test directory
    # and parse the actual keys from the `bst show` output
    #
    actual_keys = parse_output_keys(output)
    expected_keys = load_expected_keys(project_dir, actual_keys)
    mismatches = []

    for element_name in actual_keys:
        if actual_keys[element_name] != expected_keys[element_name]:
            mismatches.append(element_name)

    if mismatches:
        info = ""
        for element_name in mismatches:
            info += "  Element: {}\n".format(element_name) + \
                    "    Expected: {}\n".format(expected_keys[element_name]) + \
                    "    Actual: {}\n".format(actual_keys[element_name])

            # Write out the keys into files beside the project
            # in the temp directory so that we can easily update
            # the test when the artifact version changes.
            filename = element_filename(project_dir, element_name, "actual")
            with open(filename, "w") as f:
                f.write(actual_keys[element_name])

        raise AssertionError("Cache key mismatches occurred:\n{}\n".format(info) +
                             "New cache keys have been stored beside the " +
                             "expected ones at: {}".format(project_dir))


##############################################
#             Test Entry Point               #
##############################################

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


@pytest.mark.datafiles(DATA_DIR)
def test_cache_key(datafiles, cli):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.run(project=project, silent=True, args=[
        'show',
        '--format', '%{name}::%{full-key}',
        'target.bst'
    ])

    if result.exit_code != 0:
        raise AssertionError("BuildStream exited with code {} and output:\n{}"
                             .format(result.exit_code, result.output))

    assert_cache_keys(project, result.output)
