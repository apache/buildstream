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
#  Authors:
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

import os

#
# Private module declaring some info about where the buildstream
# is installed so we can lookup package relative resources easily
#

# The package root, wherever we are running the package from
root = os.path.dirname(os.path.abspath(__file__))

# The Element plugin directory
element_plugins = os.path.join(root, "plugins", "elements")

# The Source plugin directory
source_plugins = os.path.join(root, "plugins", "sources")

# Default user configuration
default_user_config = os.path.join(root, "data", "userconfig.yaml")

# Default project configuration
default_project_config = os.path.join(root, "data", "projectconfig.yaml")

# Script template to call module building scripts
build_all_template = os.path.join(root, "data", "build-all.sh.in")

# Module building script template
build_module_template = os.path.join(root, "data", "build-module.sh.in")

# The bundled subprojects directory
subprojects = os.path.join(root, "subprojects")
