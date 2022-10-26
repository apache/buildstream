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

from tests.testutils.site import pip_sample_packages  # pylint: disable=unused-import
from tests.testutils.site import SAMPLE_PACKAGES_SKIP_REASON

# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project-overrides")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif("not pip_sample_packages()", reason=SAMPLE_PACKAGES_SKIP_REASON)
def test_prepend_configure_commands(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "prepend-configure-commands")
    result = cli.run(
        project=project, silent=True, args=["show", "--deps", "none", "--format", "%{config}", "element.bst"]
    )

    result.assert_success()
    loaded = _yaml.load_data(result.output)
    config_commands = loaded.get_str_list("configure-commands")
    assert len(config_commands) == 3
    assert config_commands[0] == 'echo "Hello World!"'
