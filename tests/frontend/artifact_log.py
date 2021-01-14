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
import re
import pytest

from buildstream.testing import cli  # pylint: disable=unused-import


# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project",)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("target", ["artifact", "artifact-glob"])
@pytest.mark.parametrize("with_project", [True, False], ids=["with-project", "without-project"])
def test_artifact_log(cli, datafiles, target, with_project):
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
    result.assert_success()

    # Collect the log by running `bst artifact log` on the element name first
    result = cli.run(project=project, args=["artifact", "log", "target.bst"])
    result.assert_success()
    log = result.output
    assert log != ""

    # Delete the project.conf if we're going to try this without a project
    if not with_project:
        os.remove(os.path.join(project, "project.conf"))

    args = ["artifact", "log"]
    if target == "artifact":
        args.append("test/target/{}".format(key))
    elif target == "artifact-glob":
        args.append("test/target/*")

    # Run bst artifact log
    result = cli.run(project=project, args=args)
    result.assert_success()
    assert result.output == log


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
    pattern = r"\[..:..:..\] LOG     \[.*\] target.bst"
    with open(target, "r") as f:
        data = f.read()
        assert len(re.findall(pattern, data, re.MULTILINE)) > 0

    pattern = r"\[..:..:..\] LOG     \[.*\] import-bin.bst"
    with open(import_bin, "r") as f:
        data = f.read()
        assert len(re.findall(pattern, data, re.MULTILINE)) > 0
