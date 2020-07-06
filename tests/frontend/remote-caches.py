#
#  Copyright (C) 2019 Bloomberg Finance LP
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

from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream import _yaml

from tests.testutils import create_artifact_share, create_element_size

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


def message_handler(message, context):
    pass


@pytest.mark.datafiles(DATA_DIR)
def test_source_artifact_caches(cli, tmpdir, datafiles):
    cachedir = os.path.join(str(tmpdir), "cache")
    project_dir = str(datafiles)
    element_path = os.path.join(project_dir, "elements")

    with create_artifact_share(os.path.join(str(tmpdir), "share")) as share:
        user_config_file = str(tmpdir.join("buildstream.conf"))
        user_config = {
            "scheduler": {"pushers": 1},
            "source-caches": {"url": share.repo, "push": True,},
            "artifacts": {"url": share.repo, "push": True,},
            "cachedir": cachedir,
        }
        _yaml.roundtrip_dump(user_config, file=user_config_file)
        cli.configure(user_config)

        create_element_size("repo.bst", project_dir, element_path, [], 10000)

        res = cli.run(project=project_dir, args=["build", "repo.bst"])
        res.assert_success()
        assert "Pushed source " in res.stderr
        assert "Pushed artifact " in res.stderr

        # delete local sources and artifacts and check it pulls them
        shutil.rmtree(os.path.join(cachedir, "cas"))
        shutil.rmtree(os.path.join(cachedir, "sources"))

        # this should just fetch the artifacts
        res = cli.run(project=project_dir, args=["build", "repo.bst"])
        res.assert_success()
        assert "Pulled artifact " in res.stderr
        assert "Pulled source " not in res.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_source_cache_empty_artifact_cache(cli, tmpdir, datafiles):
    cachedir = os.path.join(str(tmpdir), "cache")
    project_dir = str(datafiles)
    element_path = os.path.join(project_dir, "elements")

    with create_artifact_share(os.path.join(str(tmpdir), "share")) as share:
        user_config_file = str(tmpdir.join("buildstream.conf"))
        user_config = {
            "scheduler": {"pushers": 1},
            "source-caches": {"url": share.repo, "push": True,},
            "artifacts": {"url": share.repo, "push": True,},
            "cachedir": cachedir,
        }
        _yaml.roundtrip_dump(user_config, file=user_config_file)
        cli.configure(user_config)

        create_element_size("repo.bst", project_dir, element_path, [], 10000)

        res = cli.run(project=project_dir, args=["source", "push", "repo.bst"])
        res.assert_success()
        assert "Pushed source " in res.stderr

        # delete local sources and check it pulls sources, builds
        # and then pushes the artifacts
        shutil.rmtree(os.path.join(cachedir, "cas"))
        shutil.rmtree(os.path.join(cachedir, "sources"))

        res = cli.run(project=project_dir, args=["build", "repo.bst"])
        res.assert_success()
        assert "Remote ({}) does not have artifact ".format(share.repo) in res.stderr
        assert "Pulled source" in res.stderr
        assert "Caching artifact" in res.stderr
        assert "Pushed artifact" in res.stderr
