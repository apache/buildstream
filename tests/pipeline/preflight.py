import os
import pytest

from buildstream._exceptions import ErrorDomain
from tests.testutils.runcli import cli

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'preflight-error',
)


@pytest.mark.datafiles(DATA_DIR)
def test_load_simple(cli, datafiles, tmpdir):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)

    # Lets try to fetch it...
    result = cli.run(project=basedir, args=['fetch', 'error.bst'])
    result.assert_main_error(ErrorDomain.SOURCE, "the-preflight-error")
