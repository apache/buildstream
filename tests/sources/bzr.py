# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream.testing import create_repo
from buildstream.testing import generate_element
from buildstream.testing._utils.site import HAVE_BZR

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "bzr")


@pytest.mark.skipif(HAVE_BZR is False, reason="bzr is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_fetch_checkout(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    repo = create_repo("bzr", str(tmpdir))
    ref = repo.create(os.path.join(project, "basic"))

    # Write out our test target
    element = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
    generate_element(project, "target.bst", element)

    # Fetch, build, checkout
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    assert result.exit_code == 0
    result = cli.run(project=project, args=["build", "target.bst"])
    assert result.exit_code == 0
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    assert result.exit_code == 0

    # Assert we checked out the file as it was commited
    with open(os.path.join(checkoutdir, "test")) as f:
        text = f.read()

    assert text == "test\n"
