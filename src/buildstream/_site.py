#
#  Copyright (C) 2016 Codethink Limited
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
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
