# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream.testing import create_repo
from buildstream.testing import generate_element
from buildstream.testing._utils.site import HAVE_GIT

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "no-fetch-cached")


##################################################################
#                              Tests                             #
##################################################################
# Test that fetch() is not called for cached sources
@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(DATA_DIR)
def test_no_fetch_cached(cli, tmpdir, datafiles):
    project = str(datafiles)

    # Create the repo from 'files' subdir
    repo = create_repo("git", str(tmpdir))
    ref = repo.create(os.path.join(project, "files"))

    # Write out test target with a cached and a non-cached source
    element = {"kind": "import", "sources": [repo.source_config(ref=ref), {"kind": "always_cached"}]}
    generate_element(project, "target.bst", element)

    # Test fetch of target with a cached and a non-cached source
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_success()
