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
@pytest.mark.parametrize(
    "option_name,option_value,var_name,var_value",
    [
        # Test boolean
        ("bool_export", "False", "exported-bool", "0"),
        ("bool_export", "True", "exported-bool", "1"),
        # Enum
        ("enum_export", "pony", "exported-enum", "pony"),
        ("enum_export", "horsy", "exported-enum", "horsy"),
        # Flags
        ("flags_export", "pony", "exported-flags", "pony"),
        ("flags_export", "pony, horsy", "exported-flags", "horsy,pony"),
    ],
)
def test_export(cli, datafiles, option_name, option_value, var_name, var_value):
    project = os.path.join(datafiles.dirname, datafiles.basename, "option-exports")
    result = cli.run(
        project=project,
        silent=True,
        args=["--option", option_name, option_value, "show", "--deps", "none", "--format", "%{vars}", "element.bst"],
    )

    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_str(var_name) == var_value
