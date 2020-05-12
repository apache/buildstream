# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

#
# This test case tests the failure modes of loading a plugin
# after it has already been discovered via it's origin.
#

import os
import pytest

from buildstream._exceptions import ErrorDomain
from tests.testutils import cli  # pylint: disable=unused-import
from buildstream import _yaml


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "bst2")


# Sets up the element.bst file so that it requires a source
# or element plugin.
#
def setup_element(project_path, plugin_type, plugin_name):
    element_path = os.path.join(project_path, "element.bst")

    if plugin_type == "elements":
        element = {"kind": plugin_name}
    else:
        element = {"kind": "manual", "sources": [{"kind": plugin_name}]}

    _yaml.dump(element, element_path)


####################################################
#                     Tests                        #
####################################################
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", ["elements", "sources"])
@pytest.mark.parametrize("plugin", ["bst2", "malformed"])
def test_plugin_bst2(cli, datafiles, plugin_type, plugin):
    project = str(datafiles)
    project_conf_path = os.path.join(project, "project.conf")
    project_conf = {
        "name": "test",
        "plugins": [
            {
                "origin": "local",
                "path": plugin_type,
                plugin_type: {
                    plugin: 0
                }
            }
        ]
    }
    _yaml.dump(project_conf, project_conf_path)

    setup_element(project, plugin_type, plugin)

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.PLUGIN, "plugin-version-mismatch")
