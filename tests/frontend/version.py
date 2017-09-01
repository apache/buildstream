from click.testing import CliRunner
import pytest

# For utils.get_bst_version()
from buildstream import utils

# Import the main cli entrypoint
from buildstream._frontend.main import cli


def assert_version(cli_version_output):
    major, minor = utils.get_bst_version()
    expected_start = "cli, version {}.{}".format(major, minor)
    if not cli_version_output.startswith(expected_start):
        raise AssertionError("Version output expected to begin with '{}',"
                             .format(expected_start) +
                             " output was: {}"
                             .format(cli_version_output))


@pytest.fixture(scope="module")
def runner():
    return CliRunner()


def test_version(runner):
    result = runner.invoke(cli, ['--version'])
    assert result.exit_code == 0
    assert_version(result.output)
