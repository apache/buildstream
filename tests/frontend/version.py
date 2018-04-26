from tests.testutils.runcli import cli

# For utils.get_bst_version()
from buildstream import utils


def assert_version(cli_version_output):
    major, minor = utils.get_bst_version()
    expected_start = "{}.{}".format(major, minor)
    if not cli_version_output.startswith(expected_start):
        raise AssertionError("Version output expected to begin with '{}',"
                             .format(expected_start) +
                             " output was: {}"
                             .format(cli_version_output))


def test_version(cli):
    result = cli.run(args=['--version'])
    result.assert_success()
    assert_version(result.output)
