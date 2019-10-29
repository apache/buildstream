#
#  Copyright (C) 2019 Bloomberg Finance LP
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

import os

from buildstream import utils


# symlink_host_tools_to_dir()
#
# Ensure the specified tools are symlinked into the supplied directory.
#
# Create # the directory if it doesn't exist.
#
# This is useful for isolating tests, such that only the specified tools are
# available.
#
# Args:
#   host_tools (List[str]): The string names of the tools, e.g. ['git', 'bzr'].
#   dir_       (path-like): The path to put the symlinks into.
#
def symlink_host_tools_to_dir(host_tools, dir_):
    os.makedirs(dir_, exist_ok=True)
    for tool in host_tools:
        target_path = os.path.join(dir_, tool)
        os.symlink(utils.get_host_tool(tool), str(target_path))
