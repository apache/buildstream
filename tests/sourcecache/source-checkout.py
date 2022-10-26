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
#  Authors:
#        Raoul Hidalgo Charman <raoul.hidalgocharman@codethink.co.uk>
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import shutil

import pytest

from buildstream.exceptions import ErrorDomain
from buildstream._testing.runcli import cli  # pylint: disable=unused-import

from tests.testutils.element_generators import create_element_size

DATA_DIR = os.path.dirname(os.path.realpath(__file__))


@pytest.mark.datafiles(DATA_DIR)
def test_source_checkout(tmpdir, datafiles, cli):
    project_dir = os.path.join(str(tmpdir), "project")
    element_path = "elements"
    cache_dir = os.path.join(str(tmpdir), "cache")
    source_dir = os.path.join(cache_dir, "sources")

    cli.configure(
        {
            "cachedir": cache_dir,
        }
    )
    target_dir = os.path.join(str(tmpdir), "target")

    repo = create_element_size("target.bst", project_dir, element_path, [], 100000)

    # check implicit fetching
    res = cli.run(project=project_dir, args=["source", "checkout", "--directory", target_dir, "target.bst"])
    res.assert_success()
    assert "Fetching" in res.stderr

    # remove the directory and check source checkout works with sources only in
    # the CAS
    shutil.rmtree(repo.repo)
    shutil.rmtree(target_dir)
    shutil.rmtree(source_dir)

    res = cli.run(project=project_dir, args=["source", "checkout", "--directory", target_dir, "target.bst"])
    res.assert_success()
    assert "Fetching" not in res.stderr

    # remove the CAS and check it doesn't work again
    shutil.rmtree(target_dir)
    shutil.rmtree(os.path.join(cache_dir, "cas"))

    res = cli.run(project=project_dir, args=["source", "checkout", "--directory", target_dir, "target.bst"])
    res.assert_task_error(ErrorDomain.SOURCE, None)
