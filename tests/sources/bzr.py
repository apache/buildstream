import os
import pytest

from buildstream._pipeline import PipelineError
from buildstream import _yaml

from tests.testutils import cli, create_repo
from tests.testutils.site import HAVE_BZR

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'bzr'
)


@pytest.mark.skipif(HAVE_BZR is False, reason="bzr is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_fetch_checkout(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), 'checkout')

    repo = create_repo('bzr', str(tmpdir))
    ref = repo.create(os.path.join(project, 'basic'))

    # Write out our test target
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config(ref=ref)
        ]
    }
    _yaml.dump(element, os.path.join(project, 'target.bst'))

    # Fetch, build, checkout
    result = cli.run(project=project, args=['fetch', 'target.bst'])
    assert result.exit_code == 0
    result = cli.run(project=project, args=['build', 'target.bst'])
    assert result.exit_code == 0
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    assert result.exit_code == 0

    # Assert we checked out the file as it was commited
    with open(os.path.join(checkoutdir, 'test')) as f:
        text = f.read()

    assert text == 'test\n'
