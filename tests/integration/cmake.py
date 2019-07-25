# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream.testing.integration import assert_contains
from buildstream.testing._utils.site import HAVE_SANDBOX


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
@pytest.mark.xfail(HAVE_SANDBOX == 'buildbox', reason='Not working with BuildBox')
# Not stricked xfail as only fails in CI
def test_cmake_build(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, 'checkout')
    element_name = 'cmake/cmakehello.bst'

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['artifact', 'checkout', element_name, '--directory', checkout])
    assert result.exit_code == 0

    assert_contains(checkout, ['/usr', '/usr/bin', '/usr/bin/hello'])


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
@pytest.mark.xfail(HAVE_SANDBOX == 'buildbox', reason='Not working with BuildBox', strict=True)
def test_cmake_confroot_build(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, 'checkout')
    element_name = 'cmake/cmakeconfroothello.bst'

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['artifact', 'checkout', element_name, '--directory', checkout])
    assert result.exit_code == 0

    assert_contains(checkout, ['/usr', '/usr/bin', '/usr/bin/hello'])


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
@pytest.mark.xfail(HAVE_SANDBOX == 'buildbox', reason='Not working with BuildBox')
# Not stricked xfail as only fails in CI
def test_cmake_run(cli, datafiles):
    project = str(datafiles)
    element_name = 'cmake/cmakehello.bst'

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['shell', element_name, '/usr/bin/hello'])
    assert result.exit_code == 0

    assert result.output == """Hello World!
This is hello.
"""
