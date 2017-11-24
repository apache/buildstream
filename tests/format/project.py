import os
import pytest
from buildstream import _yaml
from buildstream._exceptions import LoadError, LoadErrorReason
from tests.testutils.runcli import cli


# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


@pytest.mark.datafiles(DATA_DIR)
def test_project_conf_duplicate_plugins(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, 'duplicate-plugins')
    result = cli.run(project=project, silent=True, args=[
        'show', 'element.bst'])
    assert result.exit_code != 0
    assert result.exception
    assert isinstance(result.exception, LoadError)
    assert result.exception.reason == LoadErrorReason.INVALID_YAML
