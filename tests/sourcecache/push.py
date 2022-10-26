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
from contextlib import contextmanager, ExitStack

import pytest

from buildstream.exceptions import ErrorDomain
from buildstream._project import Project
from buildstream import _yaml
from buildstream._testing import cli  # pylint: disable=unused-import
from buildstream._testing import create_repo
from tests.testutils import create_artifact_share, dummy_context

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


def message_handler(message, is_silenced):
    pass


# Args:
#    tmpdir: A temporary directory to use as root.
#    directories: Directory names to use as cache directories.
#
@contextmanager
def _configure_caches(tmpdir, *directories):
    with ExitStack() as stack:

        def create_share(directory):
            return create_artifact_share(os.path.join(str(tmpdir), directory))

        yield (stack.enter_context(create_share(remote)) for remote in directories)


@pytest.mark.datafiles(DATA_DIR)
def test_source_push_split(cli, tmpdir, datafiles):
    cache_dir = os.path.join(str(tmpdir), "cache")
    project_dir = str(datafiles)

    with _configure_caches(tmpdir, "indexshare", "storageshare") as (index, storage):
        user_config_file = str(tmpdir.join("buildstream.conf"))
        user_config = {
            "scheduler": {"pushers": 1},
            "source-caches": {
                "servers": [
                    {"url": index.repo, "push": True, "type": "index"},
                    {"url": storage.repo, "push": True, "type": "storage"},
                ]
            },
            "cachedir": cache_dir,
        }
        _yaml.roundtrip_dump(user_config, file=user_config_file)
        cli.configure(user_config)

        repo = create_repo("tar", str(tmpdir))
        ref = repo.create(os.path.join(project_dir, "files"))
        element_path = os.path.join(project_dir, "elements")
        element_name = "push.bst"
        element = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
        _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

        # get the source object
        with dummy_context(config=user_config_file) as context:
            project = Project(project_dir, context)
            project.ensure_fully_loaded()

            element = project.load_elements(["push.bst"])[0]
            element._query_source_cache()
            assert not element._cached_sources()
            source = list(element.sources())[0]

            # check we don't have it in the current cache
            assert not index.get_source_proto(source._get_source_name())

            # build the element, this should fetch and then push the source to the
            # remote
            res = cli.run(project=project_dir, args=["build", "push.bst"])
            res.assert_success()
            assert "Pushed source" in res.stderr

            # check that we've got the remote locally now
            sourcecache = context.sourcecache
            assert sourcecache.contains(source)

            # check that the remote CAS now has it
            digest = sourcecache.export(source)._get_digest()
            assert storage.has_object(digest)


@pytest.mark.datafiles(DATA_DIR)
def test_source_push(cli, tmpdir, datafiles):
    cache_dir = os.path.join(str(tmpdir), "cache")
    project_dir = str(datafiles)

    with create_artifact_share(os.path.join(str(tmpdir), "sourceshare")) as share:
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
            "cachedir": cache_dir,
        }
        _yaml.roundtrip_dump(user_config, file=user_config_file)
        cli.configure(user_config)

        repo = create_repo("tar", str(tmpdir))
        ref = repo.create(os.path.join(project_dir, "files"))
        element_path = os.path.join(project_dir, "elements")
        element_name = "push.bst"
        element = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
        _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

        # get the source object
        with dummy_context(config=user_config_file) as context:
            project = Project(project_dir, context)
            project.ensure_fully_loaded()

            element = project.load_elements(["push.bst"])[0]
            element._query_source_cache()
            assert not element._cached_sources()
            source = list(element.sources())[0]

            # check we don't have it in the current cache
            assert not share.get_source_proto(source._get_source_name())

            # build the element, this should fetch and then push the source to the
            # remote
            res = cli.run(project=project_dir, args=["build", "push.bst"])
            res.assert_success()
            assert "Pushed source" in res.stderr

            # check that we've got the remote locally now
            sourcecache = context.sourcecache
            assert sourcecache.contains(source)

            # check that the remote CAS now has it
            digest = sourcecache.export(source)._get_digest()
            assert share.has_object(digest)


@pytest.mark.datafiles(DATA_DIR)
def test_push_pull(cli, datafiles, tmpdir):
    project_dir = str(datafiles)
    cache_dir = os.path.join(str(tmpdir), "cache")

    with create_artifact_share(os.path.join(str(tmpdir), "sourceshare")) as share:
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
            "cachedir": cache_dir,
        }
        _yaml.roundtrip_dump(user_config, file=user_config_file)
        cli.configure(user_config)

        # create repo to pull from
        repo = create_repo("tar", str(tmpdir))
        ref = repo.create(os.path.join(project_dir, "files"))
        element_path = os.path.join(project_dir, "elements")
        element_name = "push.bst"
        element = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
        _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

        res = cli.run(project=project_dir, args=["build", "push.bst"])
        res.assert_success()

        # remove local cache dir, and repo files and check it all works
        shutil.rmtree(cache_dir)
        os.makedirs(cache_dir)
        shutil.rmtree(repo.repo)

        # check it's pulls from the share
        res = cli.run(project=project_dir, args=["build", "push.bst"])
        res.assert_success()


@pytest.mark.datafiles(DATA_DIR)
def test_push_fail(cli, tmpdir, datafiles):
    project_dir = str(datafiles)
    cache_dir = os.path.join(str(tmpdir), "cache")

    # set up config with remote that we'll take down
    with create_artifact_share(os.path.join(str(tmpdir), "sourceshare")) as share:
        remote = share.repo
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
            "cachedir": cache_dir,
        }
        _yaml.roundtrip_dump(user_config, file=user_config_file)
        cli.configure(user_config)

    # create repo to pull from
    repo = create_repo("tar", str(tmpdir))
    ref = repo.create(os.path.join(project_dir, "files"))
    element_path = os.path.join(project_dir, "elements")
    element_name = "push.bst"
    element = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

    # build and check that it fails to set up the remote
    res = cli.run(project=project_dir, args=["build", "push.bst"])
    res.assert_success()

    assert "Failed to initialize remote {}".format(remote) in res.stderr
    assert "Pushing" not in res.stderr
    assert "Pushed" not in res.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_source_push_build_fail(cli, tmpdir, datafiles):
    project_dir = str(datafiles)
    cache_dir = os.path.join(str(tmpdir), "cache")

    with create_artifact_share(os.path.join(str(tmpdir), "share")) as share:
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
            "cachedir": cache_dir,
        }
        cli.configure(user_config)

        repo = create_repo("tar", str(tmpdir))
        ref = repo.create(os.path.join(project_dir, "files"))
        element_path = os.path.join(project_dir, "elements")

        element_name = "always-fail.bst"
        element = {"kind": "always_fail", "sources": [repo.source_config(ref=ref)]}
        _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

        res = cli.run(project=project_dir, args=["build", "always-fail.bst"])
        res.assert_main_error(ErrorDomain.STREAM, None)
        res.assert_task_error(ErrorDomain.ELEMENT, None)

        # Sources are still pushed after failing a build
        assert "Pushed source " in res.stderr


# Test that source push succeeds if the source needs to be fetched
# even if the artifact of the corresponding element is already cached.
@pytest.mark.datafiles(DATA_DIR)
def test_push_missing_source_after_build(cli, tmpdir, datafiles):
    cache_dir = os.path.join(str(tmpdir), "cache")
    project_dir = str(datafiles)
    element_name = "import-bin.bst"

    res = cli.run(project=project_dir, args=["build", element_name])
    res.assert_success()

    # Delete source but keep artifact in cache
    shutil.rmtree(os.path.join(cache_dir, "elementsources"))
    shutil.rmtree(os.path.join(cache_dir, "source_protos"))

    with create_artifact_share(os.path.join(str(tmpdir), "sourceshare")) as share:
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
            "cachedir": cache_dir,
        }
        _yaml.roundtrip_dump(user_config, file=user_config_file)
        cli.configure(user_config)

        res = cli.run(project=project_dir, args=["source", "push", element_name])
        res.assert_success()
        assert "fetch:{}".format(element_name) in res.stderr
        assert "Pushed source" in res.stderr


# Regression test for https://github.com/apache/buildstream/issues/1456
# Test that a build pipeline with source push enabled doesn't fail if an
# element is already cached.
@pytest.mark.datafiles(DATA_DIR)
def test_build_push_source_twice(cli, tmpdir, datafiles):
    cache_dir = os.path.join(str(tmpdir), "cache")
    project_dir = str(datafiles)
    element_name = "import-bin.bst"

    with create_artifact_share(os.path.join(str(tmpdir), "sourceshare")) as share:
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
            "cachedir": cache_dir,
        }
        _yaml.roundtrip_dump(user_config, file=user_config_file)
        cli.configure(user_config)

        res = cli.run(project=project_dir, args=["build", element_name])
        res.assert_success()
        assert "fetch:{}".format(element_name) in res.stderr
        assert "Pushed source" in res.stderr

        # The second build pipeline is a no-op as everything is already cached.
        # However, this verifies that the pipeline behaves as expected.
        res = cli.run(project=project_dir, args=["build", element_name])
        res.assert_success()
        assert "fetch:{}".format(element_name) not in res.stderr
        assert "Pushed source" not in res.stderr
