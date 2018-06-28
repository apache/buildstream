import os
import pytest

from buildstream._exceptions import ErrorDomain

from tests.testutils import cli


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "missing-command"
)


@pytest.mark.datafiles(DATA_DIR)
def test_missing_command(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.run(project=project, args=['build', 'no-runtime.bst'])
    result.assert_task_error(ErrorDomain.SANDBOX, 'missing-command')
