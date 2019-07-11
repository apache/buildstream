import os
import pytest

from buildstream.testing._utils.site import HAVE_SANBOX


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


@pytest.mark.skipif(HAVE_SANBOX, reason='Chroot equivalent test')
@pytest.mark.datafiles(DATA_DIR)
def test_sandbox_chroot_permission_denied(cli, datafiles):
    project = str(datafiles)
    element_name = 'sandbox-bwrap/non-executable-shell-success.bst'

    result = cli.run(project=project, args=['build', element_name])
    result.assert_task_error(error_domain=ErrorDomain.SANDBOX)
