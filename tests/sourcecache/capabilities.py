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
from buildstream._project import Project

from buildstream import _yaml
from buildstream._testing.runcli import cli  # pylint: disable=unused-import
from tests.testutils import dummy_context

from tests.testutils.artifactshare import create_dummy_artifact_share


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


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
            "source-caches": {
                "servers": [
                    {
                        "url": share.repo,
                    }
                ]
            },
            "cachedir": cache_dir,
        }
        _yaml.roundtrip_dump(user_config, file=user_config_file)

        with dummy_context(config=user_config_file) as context:
            # Load the project
            project = Project(project_dir, context)
            project.ensure_fully_loaded()

            # Initialize remotes
            context.initialize_remotes(True, True, None, None)

            # Create a local artifact cache handle
            sourcecache = context.sourcecache

            assert (
                not sourcecache.has_fetch_remotes()
            ), "System didn't realize the source cache didn't support BuildStream"
