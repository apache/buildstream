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
from buildstream._testing.runcli import cli  # pylint: disable=unused-import

# Project directory
DATA_DIR = os.path.dirname(os.path.realpath(__file__))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("arch", [("i686"), ("x86_64")])
def test_override(cli, datafiles, arch):
    project = os.path.join(datafiles.dirname, datafiles.basename, "option-overrides")

    bst_args = ["--option", "arch", arch]
    bst_args += ["show", "--deps", "none", "--format", "%{vars}", "element.bst"]
    result = cli.run(project=project, silent=True, args=bst_args)
    result.assert_success()

    # See the associated project.conf for the expected values
    expected_value = "--host={}-unknown-linux-gnu".format(arch)

    loaded = _yaml.load_data(result.output)
    assert loaded.get_str("conf-global") == expected_value
