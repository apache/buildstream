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

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

from collections import OrderedDict
import os

import pytest

from buildstream.testing._cachekeys import check_cache_key_stability, _parse_output_keys
from buildstream.testing.runcli import cli  # pylint: disable=unused-import
from buildstream.testing._utils.site import HAVE_BZR, HAVE_GIT, IS_LINUX, MACHINE_ARCH
from buildstream.plugin import CoreWarnings
from buildstream import _yaml


# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project",)


# The cache key test uses a project which exercises all plugins,
# so we cant run it at all if we dont have them installed.
#
@pytest.mark.skipif(MACHINE_ARCH != "x86-64", reason="Cache keys depend on architecture")
@pytest.mark.skipif(not IS_LINUX, reason="Only available on linux")
@pytest.mark.skipif(HAVE_BZR is False, reason="bzr is not available")
@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(DATA_DIR)
def test_cache_key(datafiles, cli):
    project = str(datafiles)

    # Workaround bug in recent versions of setuptools: newer
    # versions of setuptools fail to preserve symbolic links
    # when creating a source distribution, causing this test
    # to fail from a dist tarball.
    goodbye_link = os.path.join(project, "files", "local", "usr", "bin", "goodbye")
    os.unlink(goodbye_link)
    os.symlink("hello", goodbye_link)
    # pytest-datafiles does not copy mode bits
    # https://github.com/omarkohl/pytest-datafiles/issues/11
    os.chmod(goodbye_link, 0o755)

    check_cache_key_stability(project, cli)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "first_warnings, second_warnings, identical_keys",
    [
        [[], [], True],
        [[], [CoreWarnings.REF_NOT_IN_TRACK], False],
        [[CoreWarnings.REF_NOT_IN_TRACK], [], False],
        [[CoreWarnings.REF_NOT_IN_TRACK], [CoreWarnings.REF_NOT_IN_TRACK], True],
        [
            [CoreWarnings.REF_NOT_IN_TRACK, CoreWarnings.OVERLAPS],
            [CoreWarnings.OVERLAPS, CoreWarnings.REF_NOT_IN_TRACK],
            True,
        ],
    ],
)
def test_cache_key_fatal_warnings(cli, tmpdir, first_warnings, second_warnings, identical_keys):

    # Builds project, Runs bst show, gathers cache keys
    def run_get_cache_key(project_name, warnings):
        config = {"name": project_name, "min-version": "2.0", "element-path": "elements", "fatal-warnings": warnings}

        project_dir = tmpdir.mkdir(project_name)
        project_config_file = str(project_dir.join("project.conf"))
        _yaml.roundtrip_dump(config, file=project_config_file)

        elem_dir = project_dir.mkdir("elements")
        element_file = str(elem_dir.join("stack.bst"))
        _yaml.roundtrip_dump({"kind": "stack"}, file=element_file)

        result = cli.run(project=str(project_dir), args=["show", "--format", "%{name}::%{full-key}", "stack.bst"])
        return result.output

    # Returns true if all keys are identical
    def compare_cache_keys(first_keys, second_keys):
        return not any((x != y for x, y in zip(first_keys, second_keys)))

    first_keys = run_get_cache_key("first", first_warnings)
    second_keys = run_get_cache_key("second", second_warnings)

    assert compare_cache_keys(first_keys, second_keys) == identical_keys


@pytest.mark.datafiles(DATA_DIR)
def test_keys_stable_over_targets(cli, datafiles):
    root_element = "elements/key-stability/top-level.bst"
    target1 = "elements/key-stability/t1.bst"
    target2 = "elements/key-stability/t2.bst"

    project = str(datafiles)
    full_graph_result = cli.run(project=project, args=["show", "--format", "%{name}::%{full-key}", root_element])
    full_graph_result.assert_success()
    all_cache_keys = _parse_output_keys(full_graph_result.output)

    ordering1_result = cli.run(project=project, args=["show", "--format", "%{name}::%{full-key}", target1, target2])
    ordering1_result.assert_success()
    ordering1_cache_keys = _parse_output_keys(ordering1_result.output)

    ordering2_result = cli.run(project=project, args=["show", "--format", "%{name}::%{full-key}", target2, target1])
    ordering2_result.assert_success()
    ordering2_cache_keys = _parse_output_keys(ordering2_result.output)

    elements = ordering1_cache_keys.keys()

    assert {key: ordering2_cache_keys[key] for key in elements} == ordering1_cache_keys
    assert {key: all_cache_keys[key] for key in elements} == ordering1_cache_keys
