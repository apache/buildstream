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
from buildstream.exceptions import ErrorDomain, LoadErrorReason


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

    source_provenance_attrs = project_config.get_mapping("source-provenance-attributes")
    source_provenance_attrs["homepage"] = "Testing"

    generate_project(project, project_config)

    # Make sure disallowed usage of top-level source proveance fails
    result = cli.run(
        project=project,
        args=["show", "target.bst"],
    )

    result.assert_main_error(ErrorDomain.SOURCE, "top-level-provenance-on-custom-implementation")


@pytest.mark.datafiles(DATA_DIR)
def test_source_provenance_no_defined_attributes(cli, datafiles):
    project = str(datafiles)

    # Set the project_dir alias in project.conf to the path to the tested project
    project_config_path = os.path.join(project, "project.conf")
    project_config = load_yaml(project_config_path)
    aliases = project_config.get_mapping("aliases")
    aliases["project_dir"] = "file://{}".format(project)

    generate_project(project, project_config)

    # Make sure a non-default attribute fails
    result = cli.run(
        project=project,
        args=["show", "--format", "%{source-info}", "target_a.bst"],
    )
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.UNDEFINED_SOURCE_PROVENANCE_ATTRIBUTE)

    # Make sure a default attribute fails
    result = cli.run(
        project=project,
        args=["show", "--format", "%{source-info}", "target_b.bst"],
    )
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.UNDEFINED_SOURCE_PROVENANCE_ATTRIBUTE)


# Test that no defined source provenance attributes blocks all source provenance data
@pytest.mark.datafiles(DATA_DIR)
def test_source_provenance_default_attributes(cli, datafiles):
    project = str(datafiles)

    # Set the project_dir alias in project.conf to the path to the tested project
    project_config_path = os.path.join(project, "project.conf")
    project_config = load_yaml(project_config_path)
    aliases = project_config.get_mapping("aliases")
    aliases["project_dir"] = "file://{}".format(project)

    # Edit config to fallback to default source provenance attributes
    project_config.safe_del("source-provenance-attributes")

    generate_project(project, project_config)

    # Make sure defined attributes are available
    result = cli.run(
        project=project,
        args=["show", "--format", "%{source-info}", "target_b.bst"],
    )
    result.assert_success()

    provenance_result = ""
    for line in result.output.split("\n"):
        if "provenance:" in line or "    " in line:
            provenance_result += line

    assert provenance_result == "  provenance:    homepage: foo"

    # Make sure undefined attributes fail
    result = cli.run(
        project=project,
        args=["show", "--format", "%{source-info}", "target_a.bst"],
    )
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.UNDEFINED_SOURCE_PROVENANCE_ATTRIBUTE)


# Test that no defined source provenance attributes blocks all source provenance data
@pytest.mark.datafiles(DATA_DIR)
def test_source_provenance_project_defined_attributes(cli, datafiles):
    project = str(datafiles)

    # Set the project_dir alias in project.conf to the path to the tested project
    project_config_path = os.path.join(project, "project.conf")
    project_config = load_yaml(project_config_path)
    aliases = project_config.get_mapping("aliases")
    aliases["project_dir"] = "file://{}".format(project)

    # Edit config to only use project specified source provenance attributes

    source_provenance_attrs = project_config.get_mapping("source-provenance-attributes")
    source_provenance_attrs["originator"] = "Testing"

    generate_project(project, project_config)

    # Make sure defined attributes are available
    result = cli.run(
        project=project,
        args=["show", "--format", "%{source-info}", "target_a.bst"],
    )
    result.assert_success()

    provenance_result = ""
    for line in result.output.split("\n"):
        if "provenance:" in line or "    " in line:
            provenance_result += line

    assert provenance_result == "  provenance:    originator: bar"

    # Make sure undefined attributes fail
    result = cli.run(
        project=project,
        args=["show", "--format", "%{source-info}", "target_b.bst"],
    )
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.UNDEFINED_SOURCE_PROVENANCE_ATTRIBUTE)
