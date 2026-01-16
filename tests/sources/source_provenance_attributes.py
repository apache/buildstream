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

from buildstream._testing import generate_project, load_yaml
from buildstream._testing import cli  # pylint: disable=unused-import
from buildstream.exceptions import ErrorDomain


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "source_provenance_attributes")


##################################################################
#                              Tests                             #
##################################################################
# Test that no defined source provenance attributes blocks all source provenance data
@pytest.mark.datafiles(DATA_DIR)
def test_source_provenance_disallow_top_level(cli, datafiles):
    project = str(datafiles)

    # Set the project_dir alias in project.conf to the path to the tested project
    project_config_path = os.path.join(project, "project.conf")
    project_config = load_yaml(project_config_path)
    aliases = project_config.get_mapping("aliases")
    aliases["project_dir"] = "file://{}".format(project)

    generate_project(project, project_config)

    # Make sure disallowed usage of top-level source proveance fails
    result = cli.run(
        project=project,
        args=["show", "target.bst"],
    )

    result.assert_main_error(ErrorDomain.SOURCE, "top-level-provenance-on-custom-implementation")
