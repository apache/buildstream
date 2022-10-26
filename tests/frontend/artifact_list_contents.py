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
    "project",
)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("target", ["element-name", "artifact-name"])
@pytest.mark.parametrize("with_project", [True, False], ids=["with-project", "without-project"])
def test_artifact_list_exact_contents(cli, datafiles, target, with_project):
    project = str(datafiles)

    # Get the cache key of our test element
    key = cli.get_element_key(project, "import-bin.bst")

    # Ensure we have an artifact to read
    result = cli.run(project=project, args=["build", "import-bin.bst"])
    result.assert_success()

    if target == "element-name":
        arg = "import-bin.bst"
    elif target == "artifact-name":
        key = cli.get_element_key(project, "import-bin.bst")
        arg = "test/import-bin/" + key

    # Delete the project.conf if we're going to try this without a project
    if not with_project:
        os.remove(os.path.join(project, "project.conf"))

    # List the contents via the key
    result = cli.run(project=project, args=["artifact", "list-contents", arg])

    # Expect to fail if we try to list by element name and there is no project
    if target == "element-name" and not with_project:
        result.assert_main_error(ErrorDomain.STREAM, "project-not-loaded")
    else:
        result.assert_success()

        expected_output_template = "{target}:\n\tusr\n\tusr/bin\n\tusr/bin/hello\n\n"
        expected_output = expected_output_template.format(target=arg)
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

    # Ensure we have an artifact to read
    result = cli.run(project=project, args=["build", "import-bin.bst"])
    assert result.exit_code == 0

    if target == "element-name":
        arg = "import-bin.bst"
    elif target == "artifact-name":
        key = cli.get_element_key(project, "import-bin.bst")
        arg = "test/import-bin/" + key

    # List the contents via the element name
    result = cli.run(project=project, args=["artifact", "list-contents", "--long", arg])
    assert result.exit_code == 0
    expected_output_template = (
        "{target}:\n"
        "\tdrwxr-xr-x  dir    0           usr\n"
        "\tdrwxr-xr-x  dir    0           usr/bin\n"
        "\t-rw-r--r--  reg    28          usr/bin/hello\n\n"
    )
    expected_output = expected_output_template.format(target=arg)

    assert expected_output in result.output


@pytest.mark.datafiles(DATA_DIR)
def test_artifact_list_exact_contents_glob(cli, datafiles):
    project = str(datafiles)

    # Ensure we have an artifact to read
    result = cli.run(project=project, args=["build", "target.bst"])
    assert result.exit_code == 0

    # List the contents via glob
    result = cli.run(project=project, args=["artifact", "list-contents", "test/**"])
    assert result.exit_code == 0

    # get the cahe keys for each element in the glob
    import_bin_key = cli.get_element_key(project, "import-bin.bst")
    import_dev_key = cli.get_element_key(project, "import-dev.bst")
    compose_all_key = cli.get_element_key(project, "compose-all.bst")
    target_key = cli.get_element_key(project, "target.bst")

    expected_artifacts = [
        "test/import-bin/" + import_bin_key,
        "test/import-dev/" + import_dev_key,
        "test/compose-all/" + compose_all_key,
        "test/target/" + target_key,
    ]

    for artifact in expected_artifacts:
        assert artifact in result.output
