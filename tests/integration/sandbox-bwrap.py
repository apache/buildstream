import os
import pytest

from tests.testutils import cli_integration as cli
from tests.testutils.integration import assert_contains
from tests.testutils.site import HAVE_BWRAP


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


# Bubblewrap sandbox doesn't remove the dirs it created during its execution,
# so BuildStream tries to remove them to do good. BuildStream should be extra
# careful when those folders already exist and should not touch them, though.
@pytest.mark.integration
@pytest.mark.skipif(not HAVE_BWRAP, reason='Only available with bubblewrap')
@pytest.mark.datafiles(DATA_DIR)
def test_sandbox_bwrap_cleanup_build(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    # This element depends on a base image with non-empty `/tmp` folder.
    element_name = 'sandbox-bwrap/test-cleanup.bst'

    # Here, BuildStream should not attempt any rmdir etc.
    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0
