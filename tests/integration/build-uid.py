import os
import pytest

from buildstream import _yaml

from tests.testutils import cli_integration as cli
from tests.testutils.integration import assert_contains
from tests.testutils.site import IS_LINUX


pytestmark = pytest.mark.integration

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_build_uid_overridden(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_name = 'build-uid/build-uid.bst'

    project_config = {
        'name': 'build-uid-test',
        'sandbox': {
            'build-uid': 800,
            'build-gid': 900
        }
    }

    result = cli.run(project=project, project_config=project_config, args=['build', element_name])
    assert result.exit_code == 0


@pytest.mark.skipif(not IS_LINUX, reason='Only available on linux')
@pytest.mark.datafiles(DATA_DIR)
def test_build_uid_in_project(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_name = 'build-uid/build-uid-1023.bst'

    project_config = {
        'name': 'build-uid-test',
        'sandbox': {
            'build-uid': 1023,
            'build-gid': 3490
        }
    }

    result = cli.run(project=project, project_config=project_config, args=['build', element_name])
    assert result.exit_code == 0


@pytest.mark.datafiles(DATA_DIR)
def test_build_uid_default(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_name = 'build-uid/build-uid-default.bst'

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0
