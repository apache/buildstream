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

from buildstream._testing import cli_integration as cli  # pylint: disable=unused-import


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


# Test that staging a file inside a directory symlink fails.
#
# Regression test for https://gitlab.com/BuildStream/buildstream/issues/270
# noinspection PyUnusedLocal
@pytest.mark.datafiles(DATA_DIR)
def test_compose_symlinks(cli, tmpdir, datafiles):
    project = str(datafiles)

    # Symlinks do not survive being placed in a source distribution
    # ('setup.py sdist'), so we have to create the one we need here.
    project_files = os.path.join(project, "files", "compose-symlinks", "base")
    symlink_file = os.path.join(project_files, "sbin")
    os.symlink(os.path.join("usr", "sbin"), symlink_file, target_is_directory=True)

    result = cli.run(project=project, args=["build", "compose-symlinks/compose.bst"])

    assert result.exit_code == -1
    assert "Destination is a symlink, not a directory: /sbin" in result.stderr
