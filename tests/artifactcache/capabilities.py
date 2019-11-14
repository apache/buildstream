# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os

import pytest
from buildstream._project import Project

from buildstream import _yaml
from buildstream.testing.runcli import cli  # pylint: disable=unused-import
from tests.testutils import dummy_context

from tests.testutils.artifactshare import create_dummy_artifact_share


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project",)


@pytest.mark.datafiles(DATA_DIR)
def test_artifact_cache_with_missing_capabilities_is_skipped(cli, tmpdir, datafiles):
    project_dir = str(datafiles)

    # Set up an artifact cache.
    with create_dummy_artifact_share() as share:
        # Configure artifact share
        cache_dir = os.path.join(str(tmpdir), "cache")
        user_config_file = str(tmpdir.join("buildstream.conf"))
        user_config = {
            "scheduler": {"pushers": 1},
            "artifacts": {"url": share.repo, "push": True,},
            "cachedir": cache_dir,
        }
        _yaml.roundtrip_dump(user_config, file=user_config_file)

        with dummy_context(config=user_config_file) as context:
            # Load the project
            project = Project(project_dir, context)
            project.ensure_fully_loaded()

            # Create a local artifact cache handle
            artifactcache = context.artifactcache

            # Manually setup the CAS remote
            artifactcache.setup_remotes(use_config=True)

            assert (
                not artifactcache.has_fetch_remotes()
            ), "System didn't realize the artifact cache didn't support BuildStream"
