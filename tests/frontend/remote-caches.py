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

from buildstream._testing import cli  # pylint: disable=unused-import
from buildstream import _yaml

from tests.testutils import create_artifact_share, create_element_size

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


def message_handler(message, context):
    pass


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout(cli, tmpdir, datafiles):
    cachedir = os.path.join(str(tmpdir), "cache")
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")

    with create_artifact_share(os.path.join(str(tmpdir), "remote-cache")) as remote_cache:
        # Enable remote cache
        cli.configure({"cache": {"storage-service": {"url": remote_cache.repo}}})

        # First build it
        result = cli.run(project=project, args=["build", "target.bst"])
        result.assert_success()

        # Discard the local CAS cache
        shutil.rmtree(str(os.path.join(cachedir, "cas")))

        # Now check it out, this should automatically fetch the necessary blobs
        # from the remote cache
        result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkout])
        result.assert_success()

        # Check that the executable hello file is found in the checkout
        filename = os.path.join(checkout, "usr", "bin", "hello")
        assert os.path.exists(filename)

        filename = os.path.join(checkout, "usr", "include", "pony.h")
        assert os.path.exists(filename)


@pytest.mark.datafiles(DATA_DIR)
def test_source_artifact_caches(cli, tmpdir, datafiles):
    cachedir = os.path.join(str(tmpdir), "cache")
    project_dir = str(datafiles)
    element_path = os.path.join(project_dir, "elements")

    with create_artifact_share(os.path.join(str(tmpdir), "share")) as share:
        user_config_file = str(tmpdir.join("buildstream.conf"))
        user_config = {
            "scheduler": {"pushers": 1},
            "source-caches": {
                "servers": [
                    {
                        "url": share.repo,
                        "push": True,
                    }
                ]
            },
            "artifacts": {
                "servers": [
                    {
                        "url": share.repo,
                        "push": True,
                    }
                ]
            },
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
            "source-caches": {
                "servers": [
                    {
                        "url": share.repo,
                        "push": True,
                    }
                ]
            },
            "artifacts": {
                "servers": [
                    {
                        "url": share.repo,
                        "push": True,
                    }
                ]
            },
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
