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

from .._exceptions import LoadError
from ..exceptions import LoadErrorReason
from .option import Option, OPTION_SYMBOLS


# OptionBool
#
# A boolean project option
#
class OptionBool(Option):

    OPTION_TYPE = "bool"

    def load(self, node):

        super().load(node)
        node.validate_keys(OPTION_SYMBOLS + ["default"])
        self.value = node.get_bool("default")

    def load_value(self, node):
        self.value = node.get_bool(self.name)

    def set_value(self, value):
        if value in ("True", "true"):
            self.value = True
        elif value in ("False", "false"):
            self.value = False
        else:
            raise LoadError(
                "Invalid value for boolean option {}: {}".format(self.name, value), LoadErrorReason.INVALID_DATA
            )

    def get_value(self):
        if self.value:
            return "1"
        else:
            return "0"
