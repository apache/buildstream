#
#  Copyright (C) 2017 Codethink Limited
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

from .. import utils
from .optionflags import OptionFlags


# OptionEltMask
#
# A flags option which automatically only allows element
# names as values.
#
class OptionEltMask(OptionFlags):

    OPTION_TYPE = "element-mask"

    def load(self, node):
        # Ask the parent constructor to disallow value definitions,
        # we define those automatically only.
        super().load_special(node, allow_value_definitions=False)

    # Here we want all valid elements as possible values,
    # but we'll settle for just the relative filenames
    # of files ending with ".bst" in the project element directory
    def load_valid_values(self, node):
        values = []
        for filename in utils.list_relative_paths(self.pool.element_path):
            if filename.endswith(".bst"):
                values.append(filename)
        return values
