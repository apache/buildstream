import os

import pexpect
from ruamel import yaml

from buildstream._versions import BST_FORMAT_VERSION
from tests.testutils.constants import PEXPECT_TIMEOUT_SHORT


def test_init(tmpdir):
    session = pexpect.spawn("bst", ["--no-colors", "init", str(tmpdir)], timeout=PEXPECT_TIMEOUT_SHORT)
    name = "test-project"
    format_version = 24
    element_path = "my-elements"

    session.expect_exact("Project name:")
    session.sendline(name)

    session.expect_exact("Format version [{}]:".format(BST_FORMAT_VERSION))
    session.sendline(str(format_version))

    session.expect_exact("Element path [elements]:")
    session.sendline(element_path)

    session.expect_exact("Created project.conf")
    session.close()

    # Now assert that a project.conf got created with expected values
    with open(os.path.join(str(tmpdir), "project.conf")) as f:
        project_conf = yaml.safe_load(f)

    assert project_conf["name"] == name
    assert project_conf["format-version"] == format_version
    assert project_conf["element-path"] == element_path
