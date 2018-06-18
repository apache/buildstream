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
import shutil
import subprocess

#
# Private module declaring some info about where the buildstream
# is installed so we can lookup package relative resources easily
#

# The package root, wherever we are running the package from
root = os.path.dirname(os.path.abspath(__file__))

# The Element plugin directory
element_plugins = os.path.join(root, 'plugins', 'elements')

# The Source plugin directory
source_plugins = os.path.join(root, 'plugins', 'sources')

# Default user configuration
default_user_config = os.path.join(root, 'data', 'userconfig.yaml')

# Default project configuration
default_project_config = os.path.join(root, 'data', 'projectconfig.yaml')

# Script template to call module building scripts
build_all_template = os.path.join(root, 'data', 'build-all.sh.in')

# Module building script template
build_module_template = os.path.join(root, 'data', 'build-module.sh.in')

# Cached bwrap version
_bwrap_major = None
_bwrap_minor = None
_bwrap_patch = None


# check_bwrap_version()
#
# Checks the version of installed bwrap against the requested version
#
# Args:
#    major (int): The required major version
#    minor (int): The required minor version
#    patch (int): The required patch level
#
# Returns:
#    (bool): Whether installed bwrap meets the requirements
#
def check_bwrap_version(major, minor, patch):
    # pylint: disable=global-statement

    global _bwrap_major
    global _bwrap_minor
    global _bwrap_patch

    # Parse bwrap version and save into cache, if not already cached
    if _bwrap_major is None:
        bwrap_path = shutil.which('bwrap')
        if not bwrap_path:
            return False
        cmd = [bwrap_path, "--version"]
        version = str(subprocess.check_output(cmd).split()[1], "utf-8")
        _bwrap_major, _bwrap_minor, _bwrap_patch = map(int, version.split("."))

    # Check whether the installed version meets the requirements
    if _bwrap_major > major:
        return True
    elif _bwrap_major < major:
        return False
    else:
        if _bwrap_minor > minor:
            return True
        elif _bwrap_minor < minor:
            return False
        else:
            return _bwrap_patch >= patch
