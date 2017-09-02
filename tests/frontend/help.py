from click.testing import CliRunner
import pytest

# Import the main cli entrypoint
from buildstream._frontend.main import cli


def assert_help(cli_output):
    expected_start = "Usage: "
    if not cli_output.startswith(expected_start):
        raise AssertionError("Help output expected to begin with '{}',"
                             .format(expected_start) +
                             " output was: {}"
                             .format(cli_output))


@pytest.fixture(scope="module")
def runner():
    return CliRunner()


def test_help_main(runner):
    result = runner.invoke(cli, ['--help'])
    assert result.exit_code == 0
    assert_help(result.output)


@pytest.mark.parametrize("command", [
    ('build'),
    ('checkout'),
    ('fetch'),
    ('pull'),
    ('push'),
    ('shell'),
    ('show'),
    ('source-bundle'),
    ('track'),
    ('workspace')
])
def test_help(runner, command):
    result = runner.invoke(cli, [command, '--help'])
    assert result.exit_code == 0
    assert_help(result.output)
