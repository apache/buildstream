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
def test_artifact_log(cli, datafiles):
    project = str(datafiles)

    # Get the cache key of our test element
    result = cli.run(
        project=project,
        silent=True,
        args=["--no-colors", "show", "--deps", "none", "--format", "%{full-key}", "target.bst"],
    )
    key = result.output.strip()

    # Ensure we have an artifact to read
    result = cli.run(project=project, args=["build", "target.bst"])
    assert result.exit_code == 0

    # Read the log via the element name
    result = cli.run(project=project, args=["artifact", "log", "target.bst"])
    assert result.exit_code == 0
    log = result.output

    # Assert that there actually was a log file
    assert log != ""

    # Read the log via the key
    result = cli.run(project=project, args=["artifact", "log", "test/target/" + key])
    assert result.exit_code == 0
    assert log == result.output

    # Read the log via glob
    result = cli.run(project=project, args=["artifact", "log", "test/target/*"])
    assert result.exit_code == 0
    # The artifact is cached under both a strong key and a weak key
    assert log == result.output


@pytest.mark.datafiles(DATA_DIR)
def test_artifact_log_files(cli, datafiles):
    project = str(datafiles)

    # Ensure we have an artifact to read
    result = cli.run(project=project, args=["build", "target.bst"])
    assert result.exit_code == 0

    logfiles = os.path.join(project, "logfiles")
    target = os.path.join(project, logfiles, "target.log")
    import_bin = os.path.join(project, logfiles, "import-bin.log")
    # Ensure the logfile doesn't exist before the command is run
    assert not os.path.exists(logfiles)
    assert not os.path.exists(target)
    assert not os.path.exists(import_bin)

    # Run the command and ensure the file now exists
    result = cli.run(project=project, args=["artifact", "log", "--out", logfiles, "target.bst", "import-bin.bst"])
    assert result.exit_code == 0
    assert os.path.exists(logfiles)
    assert os.path.exists(target)
    assert os.path.exists(import_bin)

    # Ensure the file contains the logs by checking for the LOG line
    with open(target, "r") as f:
        data = f.read()
        assert "LOG     target.bst" in data
    with open(import_bin, "r") as f:
        data = f.read()
        assert "LOG     import-bin.bst" in data
