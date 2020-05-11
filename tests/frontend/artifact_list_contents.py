#
#  Copyright (C) 2019 Codethink Limited
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import cli  # pylint: disable=unused-import


# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project",)


@pytest.mark.datafiles(DATA_DIR)
def test_artifact_list_exact_contents_element(cli, datafiles):
    project = str(datafiles)

    # Ensure we have an artifact to read
    result = cli.run(project=project, args=["build", "import-bin.bst"])
    assert result.exit_code == 0

    # List the contents via the element name
    result = cli.run(project=project, args=["artifact", "list-contents", "import-bin.bst"])
    assert result.exit_code == 0
    expected_output = "import-bin.bst:\n\tusr\n\tusr/bin\n\tusr/bin/hello\n\n"
    assert expected_output in result.output


@pytest.mark.datafiles(DATA_DIR)
def test_artifact_list_exact_contents_ref(cli, datafiles):
    project = str(datafiles)

    # Get the cache key of our test element
    key = cli.get_element_key(project, "import-bin.bst")

    # Ensure we have an artifact to read
    result = cli.run(project=project, args=["build", "import-bin.bst"])
    assert result.exit_code == 0

    # List the contents via the key
    result = cli.run(project=project, args=["artifact", "list-contents", "test/import-bin/" + key])
    assert result.exit_code == 0

    expected_output = "test/import-bin/" + key + ":\n" "\tusr\n" "\tusr/bin\n" "\tusr/bin/hello\n\n"
    assert expected_output in result.output


@pytest.mark.datafiles(DATA_DIR)
def test_artifact_list_exact_contents_glob(cli, datafiles):
    project = str(datafiles)

    # Ensure we have an artifact to read
    result = cli.run(project=project, args=["build", "target.bst"])
    assert result.exit_code == 0

    # List the contents via glob
    result = cli.run(project=project, args=["artifact", "list-contents", "test/*"])
    assert result.exit_code == 0

    # get the cahe keys for each element in the glob
    import_bin_key = cli.get_element_key(project, "import-bin.bst")
    import_dev_key = cli.get_element_key(project, "import-dev.bst")
    compose_all_key = cli.get_element_key(project, "compose-all.bst")
    target_key = cli.get_element_key(project, "target.bst")

    expected_artifacts = [
        "test/import-bin/" + import_bin_key,
        "test/import-dev/" + import_dev_key,
        "test/compose-all/" + compose_all_key,
        "test/target/" + target_key,
    ]

    for artifact in expected_artifacts:
        assert artifact in result.output


@pytest.mark.datafiles(DATA_DIR)
def test_artifact_list_exact_contents_element_long(cli, datafiles):
    project = str(datafiles)

    # Ensure we have an artifact to read
    result = cli.run(project=project, args=["build", "import-bin.bst"])
    assert result.exit_code == 0

    # List the contents via the element name
    result = cli.run(project=project, args=["artifact", "list-contents", "--long", "import-bin.bst"])
    assert result.exit_code == 0
    expected_output = (
        "import-bin.bst:\n"
        "\tdrwxr-xr-x  dir    1           usr\n"
        "\tdrwxr-xr-x  dir    1           usr/bin\n"
        "\t-rw-r--r--  reg    107         usr/bin/hello\n\n"
    )

    assert expected_output in result.output


@pytest.mark.datafiles(DATA_DIR)
def test_artifact_list_exact_contents_ref_long(cli, datafiles):
    project = str(datafiles)

    # Get the cache key of our test element
    key = cli.get_element_key(project, "import-bin.bst")

    # Ensure we have an artifact to read
    result = cli.run(project=project, args=["build", "import-bin.bst"])
    assert result.exit_code == 0

    # List the contents via the key
    result = cli.run(project=project, args=["artifact", "list-contents", "-l", "test/import-bin/" + key])
    assert result.exit_code == 0

    expected_output = (
        "  test/import-bin/" + key + ":\n"
        "\tdrwxr-xr-x  dir    1           usr\n"
        "\tdrwxr-xr-x  dir    1           usr/bin\n"
        "\t-rw-r--r--  reg    107         usr/bin/hello\n\n"
    )

    assert expected_output in result.output
