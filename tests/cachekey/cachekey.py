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
from tests.testutils.site import HAVE_BZR, HAVE_GIT, HAVE_OSTREE, IS_LINUX

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
def load_expected_keys(project_dir, actual_keys, raise_error=True):

    expected_keys = OrderedDict()
    for element_name in actual_keys:
        expected = element_filename(project_dir, element_name, 'expected')
        try:
            with open(expected, 'r') as f:
                expected_key = f.read()
                expected_key = expected_key.strip()
        except FileNotFoundError as e:
            expected_key = None
            if raise_error:
                raise Exception("Cache key test needs update, " +
                                "expected file {} not found.\n\n".format(expected) +
                                "Use tests/cachekey/update.py to automatically " +
                                "update this test case")

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

        raise AssertionError("Cache key mismatches occurred:\n{}\n".format(info) +
                             "Use tests/cachekey/update.py to automatically " +
                             "update this test case")


##############################################
#             Test Entry Point               #
##############################################

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


# The cache key test uses a project which exercises all plugins,
# so we cant run it at all if we dont have them installed.
#
@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.skipif(HAVE_BZR is False, reason="bzr is not available")
@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.skipif(HAVE_OSTREE is False, reason="ostree is not available")
@pytest.mark.datafiles(DATA_DIR)
def test_cache_key(datafiles, cli):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # Workaround bug in recent versions of setuptools: newer
    # versions of setuptools fail to preserve symbolic links
    # when creating a source distribution, causing this test
    # to fail from a dist tarball.
    goodbye_link = os.path.join(project, 'files', 'local',
                                'usr', 'bin', 'goodbye')
    os.unlink(goodbye_link)
    os.symlink('hello', goodbye_link)

    result = cli.run(project=project, silent=True, args=[
        'show',
        '--format', '%{name}::%{full-key}',
        'target.bst'
    ])
    result.assert_success()
    assert_cache_keys(project, result.output)
