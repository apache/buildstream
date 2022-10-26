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
#   Authors:
#       Benjamin Schubert (bschubert15@bloomberg.net)
#

import os

# To make use of these test utilities it is necessary to have pytest
# available. However, we don't want to have a hard dependency on
# pytest.
try:
    import pytest
except ImportError:
    module_name = globals()["__name__"]
    msg = "Could not import pytest:\n" "To use the {} module, you must have pytest installed.".format(module_name)
    raise ImportError(msg)

from buildstream import _yaml
from .. import ALL_REPO_KINDS


# kind()
#
# Pytest fixture to get all the registered source plugins.
#
# This assumes the usage of the standard `project` and will automatically
# register the plugin in the project configuration, in addition to its junction
# configuration
#
# Yields:
#   the plugin kind name
#
@pytest.fixture(params=ALL_REPO_KINDS.keys())
def kind(request, datafiles):
    # Register plugins both on the toplevel project and on its junctions
    for project_dir in [str(datafiles), os.path.join(str(datafiles), "files", "sub-project")]:
        add_plugins_conf(project_dir, request.param)

    yield request.param


# add_plugins_conf()
#
# Add the given plugin to the configuration of the given project.
#
# Args:
#   project (str): path to the project on which to register the plugin
#   plugin_kind (str): name of the plugin kind to register
#
def add_plugins_conf(project, plugin_kind):
    _scaffolder, plugin_package = ALL_REPO_KINDS[plugin_kind]

    project_conf_file = os.path.join(project, "project.conf")
    project_conf = _yaml.roundtrip_load(project_conf_file)

    if plugin_package is not None:
        project_conf["plugins"] = [
            {
                "origin": "pip",
                "package-name": plugin_package,
                "sources": [plugin_kind],
            },
        ]

    _yaml.roundtrip_dump(project_conf, project_conf_file)


# update_project_configuration()
#
# Update the project configuration with the given updated configuration.
#
# Note: This does a simple `dict.update()` call, which will not merge recursively
#       but will replace every defined key.
#
# Args:
#   project_path (str): the path to the root of the project
#   updated_configuration (dict): configuration to merge into the existing one
#
def update_project_configuration(project_path, updated_configuration):
    project_conf_path = os.path.join(project_path, "project.conf")
    project_conf = _yaml.roundtrip_load(project_conf_path)

    project_conf.update(updated_configuration)

    _yaml.roundtrip_dump(project_conf, project_conf_path)
