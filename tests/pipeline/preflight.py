import os
import pytest

from buildstream._exceptions import ErrorDomain
from tests.testutils.runcli import cli
from tests.testutils.site import IS_LINUX, NO_FUSE

pytestmark = pytest.mark.skipif(IS_LINUX and NO_FUSE, reason='FUSE not supported on this system')

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
