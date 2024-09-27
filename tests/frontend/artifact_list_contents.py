#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream._testing import cli  # pylint: disable=unused-import
from buildstream.exceptions import ErrorDomain


# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "artifact_list_contents",
)


def prepare_symlink(project):
    # Create the link before running the tests.
    # This is needed for users working on Windows, git checks out symlinks as files which content is the name
    # of the symlink and the test therefore doesn't have the correct content
    os.symlink(
        os.path.join("..", "basicfile"),
        os.path.join(project, "files", "files-and-links", "basicfolder", "basicsymlink"),
    )


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("target", ["element-name", "artifact-name"])
@pytest.mark.parametrize("with_project", [True, False], ids=["with-project", "without-project"])
def test_artifact_list_exact_contents(cli, datafiles, target, with_project):
    project = str(datafiles)
    prepare_symlink(project)

    # Ensure we have an artifact to read
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()

    if target == "element-name":
        arg_bin = "import-bin.bst"
        arg_links = "import-links.bst"
    elif target == "artifact-name":
        key_bin = cli.get_element_key(project, "import-bin.bst")
        key_links = cli.get_element_key(project, "import-links.bst")
        arg_bin = "test/import-bin/" + key_bin
        arg_links = "test/import-links/" + key_links
    else:
        assert False, "unreachable"

    # Delete the project.conf if we're going to try this without a project
    if not with_project:
        os.remove(os.path.join(project, "project.conf"))

    expected_output_bin = ("{target}:\n" "\tusr\n" "\tusr/bin\n" "\tusr/bin/hello\n\n").format(target=arg_bin)
    expected_output_links = (
        "{target}:\n" "\tbasicfile\n" "\tbasicfolder\n" "\tbasicfolder/basicsymlink\n" "\tbasicfolder/subdir-file\n\n"
    ).format(target=arg_links)

    for arg, expected_output in [(arg_bin, expected_output_bin), (arg_links, expected_output_links)]:
        # List the contents via the key
        result = cli.run(project=project, args=["artifact", "list-contents", arg])

        # Expect to fail if we try to list by element name and there is no project
        if target == "element-name" and not with_project:
            result.assert_main_error(ErrorDomain.STREAM, "project-not-loaded")
        else:
            result.assert_success()
            assert expected_output in result.output


# NOTE: The pytest-datafiles package has an issue where it fails to transfer any
#       mode bits when copying files into the temporary directory:
#
#         https://github.com/omarkohl/pytest-datafiles/issues/11
#
#       This is why the /usr/bin/hello file appears to not be executable
#       in the test below, in real life the /usr/bin/hello file will
#       appear executable.
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("target", ["element-name", "artifact-name"])
def test_artifact_list_exact_contents_long(cli, datafiles, target):
    project = str(datafiles)
    prepare_symlink(project)

    # Ensure we have an artifact to read
    result = cli.run(project=project, args=["build", "target.bst"])
    assert result.exit_code == 0

    if target == "element-name":
        arg_bin = "import-bin.bst"
        arg_links = "import-links.bst"
    elif target == "artifact-name":
        key_bin = cli.get_element_key(project, "import-bin.bst")
        key_links = cli.get_element_key(project, "import-links.bst")
        arg_bin = "test/import-bin/" + key_bin
        arg_links = "test/import-links/" + key_links
    else:
        assert False, "unreachable"

    expected_output_bin = (
        "{target}:\n"
        "\tdrwxr-xr-x  dir    0           usr\n"
        "\tdrwxr-xr-x  dir    0           usr/bin\n"
        "\t-rwxr-xr-x  exe    28          usr/bin/hello\n\n"
    ).format(target=arg_bin)
    expected_output_links = (
        "{target}:\n"
        "\t-rw-r--r--  reg    14          basicfile\n"
        "\tdrwxr-xr-x  dir    0           basicfolder\n"
        "\tlrwxrwxrwx  link   12          basicfolder/basicsymlink -> ../basicfile\n"
        "\t-rw-r--r--  reg    0           basicfolder/subdir-file\n\n"
    ).format(target=arg_links)

    # List the contents via the element name
    for arg, expected_output in [(arg_bin, expected_output_bin), (arg_links, expected_output_links)]:
        result = cli.run(project=project, args=["artifact", "list-contents", "--long", arg])
        assert result.exit_code == 0
        assert expected_output in result.output


@pytest.mark.datafiles(DATA_DIR)
def test_artifact_list_exact_contents_glob(cli, datafiles):
    project = str(datafiles)
    prepare_symlink(project)

    # Ensure we have an artifact to read
    result = cli.run(project=project, args=["build", "target.bst"])
    assert result.exit_code == 0

    # List the contents via glob
    result = cli.run(project=project, args=["artifact", "list-contents", "test/**"])
    assert result.exit_code == 0

    # get the cahe keys for each element in the glob
    import_bin_key = cli.get_element_key(project, "import-bin.bst")
    import_links_key = cli.get_element_key(project, "import-links.bst")
    target_key = cli.get_element_key(project, "target.bst")

    expected_artifacts = [
        "test/import-bin/" + import_bin_key,
        "test/import-links/" + import_links_key,
        "test/target/" + target_key,
    ]

    for artifact in expected_artifacts:
        assert artifact in result.output
