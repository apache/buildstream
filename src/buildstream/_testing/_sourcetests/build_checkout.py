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

from buildstream import _yaml
from .. import create_repo
from .. import cli  # pylint: disable=unused-import
from .utils import kind  # pylint: disable=unused-import

# Project directory
TOP_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TOP_DIR, "project")


def strict_args(args, strict):
    if strict != "strict":
        return ["--no-strict", *args]
    return args


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("strict", ["strict", "non-strict"])
def test_fetch_build_checkout(cli, tmpdir, datafiles, strict, kind):
    checkout = os.path.join(cli.directory, "checkout")
    project = str(datafiles)
    dev_files_path = os.path.join(project, "files", "dev-files")
    element_path = os.path.join(project, "elements")
    element_name = "build-test-{}.bst".format(kind)

    # Create our repo object of the given source type with
    # the dev files, and then collect the initial ref.
    #
    repo = create_repo(kind, str(tmpdir))
    ref = repo.create(dev_files_path)

    # Write out our test target
    element = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

    assert cli.get_element_state(project, element_name) == "fetch needed"
    result = cli.run(project=project, args=strict_args(["build", element_name], strict))
    result.assert_success()
    assert cli.get_element_state(project, element_name) == "cached"

    # Now check it out
    result = cli.run(
        project=project, args=strict_args(["artifact", "checkout", element_name, "--directory", checkout], strict)
    )
    result.assert_success()

    # Check that the pony.h include from files/dev-files exists
    filename = os.path.join(checkout, "usr", "include", "pony.h")
    assert os.path.exists(filename)
