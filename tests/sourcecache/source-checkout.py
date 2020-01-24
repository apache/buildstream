#
#  Copyright (C) 2018 Codethink Limited
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#        Raoul Hidalgo Charman <raoul.hidalgocharman@codethink.co.uk>
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import shutil

import pytest

from buildstream.exceptions import ErrorDomain
from buildstream.testing.runcli import cli  # pylint: disable=unused-import

from tests.testutils.element_generators import create_element_size

DATA_DIR = os.path.dirname(os.path.realpath(__file__))


@pytest.mark.datafiles(DATA_DIR)
def test_source_checkout(tmpdir, datafiles, cli):
    project_dir = os.path.join(str(tmpdir), "project")
    element_path = "elements"
    cache_dir = os.path.join(str(tmpdir), "cache")
    source_dir = os.path.join(cache_dir, "sources")

    cli.configure(
        {"cachedir": cache_dir,}
    )
    target_dir = os.path.join(str(tmpdir), "target")

    repo = create_element_size("target.bst", project_dir, element_path, [], 100000)

    # check implicit fetching
    res = cli.run(project=project_dir, args=["source", "checkout", "--directory", target_dir, "target.bst"])
    res.assert_success()
    assert "Fetching from" in res.stderr

    # remove the directory and check source checkout works with sources only in
    # the CAS
    shutil.rmtree(repo.repo)
    shutil.rmtree(target_dir)
    shutil.rmtree(source_dir)

    res = cli.run(project=project_dir, args=["source", "checkout", "--directory", target_dir, "target.bst"])
    res.assert_success()
    assert "Fetching from" not in res.stderr

    # remove the CAS and check it doesn't work again
    shutil.rmtree(target_dir)
    shutil.rmtree(os.path.join(cache_dir, "cas"))

    res = cli.run(project=project_dir, args=["source", "checkout", "--directory", target_dir, "target.bst"])
    res.assert_task_error(ErrorDomain.PLUGIN, None)
