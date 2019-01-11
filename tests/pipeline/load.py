import os
import pytest
from buildstream._exceptions import ErrorDomain
from buildstream import _yaml
from tests.testutils.runcli import cli

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'load',
)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'simple'))
def test_load_simple(cli, datafiles):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.get_element_config(basedir, 'simple.bst')

    assert(result['configure-commands'][0] == 'pony')
