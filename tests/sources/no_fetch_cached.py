import os
import pytest

from buildstream import _yaml

from buildstream.plugintestutils import cli
from tests.testutils import create_repo
from tests.testutils.site import HAVE_GIT

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'no-fetch-cached'
)


##################################################################
#                              Tests                             #
##################################################################
# Test that fetch() is not called for cached sources
@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(DATA_DIR)
def test_no_fetch_cached(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # Create the repo from 'files' subdir
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(project, 'files'))

    # Write out test target with a cached and a non-cached source
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config(ref=ref),
            {
                'kind': 'always_cached'
            }
        ]
    }
    _yaml.dump(element, os.path.join(project, 'target.bst'))

    # Test fetch of target with a cached and a non-cached source
    result = cli.run(project=project, args=[
        'source', 'fetch', 'target.bst'
    ])
    result.assert_success()
