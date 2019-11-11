# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream.testing._utils.site import HAVE_SANDBOX


pytestmark = pytest.mark.integration

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_builddir_socket_ignored(cli, datafiles):
    project = str(datafiles)
    element_name = "sockets/make-builddir-socket.bst"

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_install_root_socket_ignored(cli, datafiles):
    project = str(datafiles)
    element_name = "sockets/make-install-root-socket.bst"

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0
