#
#  Copyright (C) 2018 Codethink Limited
#  Copyright (C) 2019 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
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
            {"origin": "pip", "package-name": plugin_package, "sources": [plugin_kind],},
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
