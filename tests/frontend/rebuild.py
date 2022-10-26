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

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest
from buildstream._testing import cli  # pylint: disable=unused-import

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


def strict_args(args, strict):
    if strict != "strict":
        return ["--no-strict", *args]
    return args


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("strict", ["strict", "non-strict"])
def test_rebuild(datafiles, cli, strict):
    project = str(datafiles)

    # First build intermediate target.bst
    result = cli.run(project=project, args=strict_args(["build", "target.bst"], strict))
    result.assert_success()

    # Modify base import
    with open(os.path.join(project, "files", "dev-files", "usr", "include", "new.h"), "w", encoding="utf-8") as f:
        f.write("#define NEW")

    # Rebuild base import and build top-level rebuild-target.bst
    # In non-strict mode, this does not rebuild intermediate target.bst,
    # which means that a weakly cached target.bst will be staged as dependency.
    result = cli.run(project=project, args=strict_args(["build", "rebuild-target.bst"], strict))
    result.assert_success()

    built_elements = result.get_built_elements()

    assert "rebuild-target.bst" in built_elements
    if strict == "strict":
        assert "target.bst" in built_elements
    else:
        assert "target.bst" not in built_elements


# Test that a cached artifact matching the strict cache key is preferred
# to a more recent artifact matching only the weak cache key.
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("strict", ["strict", "non-strict"])
def test_modify_and_revert(datafiles, cli, strict):
    project = str(datafiles)

    # First build target and dependencies
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()

    # Remember cache key of first build
    target_cache_key = cli.get_element_key(project, "target.bst")

    # Modify dependency
    new_header_path = os.path.join(project, "files", "dev-files", "usr", "include", "new.h")
    with open(new_header_path, "w", encoding="utf-8") as f:
        f.write("#define NEW")

    # Trigger rebuild. This will also rebuild the unmodified target as this
    # follows a strict build plan.
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()

    assert "target.bst" in result.get_built_elements()
    assert cli.get_element_key(project, "target.bst") != target_cache_key

    # Revert previous modification in dependency
    os.unlink(new_header_path)

    # Rebuild again, everything should be cached.
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    assert len(result.get_built_elements()) == 0

    # Verify that cache key now again matches the first build in both
    # strict and non-strict mode.
    cli.configure({"projects": {"test": {"strict": strict == "strict"}}})
    assert cli.get_element_key(project, "target.bst") == target_cache_key
