import os

import pexpect

from buildstream import _yaml
from buildstream import utils
from tests.testutils.constants import PEXPECT_TIMEOUT_SHORT


def test_init(tmpdir):
    session = pexpect.spawn("bst", ["--no-colors", "init", str(tmpdir)], timeout=PEXPECT_TIMEOUT_SHORT)
    name = "test-project"
    min_version = "2.0"
    element_path = "my-elements"
    bst_major, bst_minor = utils.get_bst_version()

    # For the version check, artificially set the version to at least
    # version 2.0
    #
    # TODO: Remove this code block after releasing 2.0
    #
    if bst_major < 2:
        bst_major = 2
        bst_minor = 0

    session.expect_exact("Project name:")
    session.sendline(name)

    session.expect_exact("Minimum version [{}.{}]:".format(bst_major, bst_minor))
    session.sendline(str(min_version))

    session.expect_exact("Element path [elements]:")
    session.sendline(element_path)

    session.expect_exact("Created project.conf")
    session.close()

    # Now assert that a project.conf got created with expected values
    project_conf = _yaml.load(os.path.join(str(tmpdir), "project.conf"), shortname=None)
    assert project_conf.get_str("name") == name
    assert project_conf.get_str("min-version") == min_version
    assert project_conf.get_str("element-path") == element_path
