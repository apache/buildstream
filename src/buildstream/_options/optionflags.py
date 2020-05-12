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


# OptionFlags
#
# A flags project option
#
class OptionFlags(Option):

    OPTION_TYPE = "flags"

    def __init__(self, name, definition, pool):
        self.values = None
        super().__init__(name, definition, pool)

    def load(self, node):
        self.load_special(node)

    def load_special(self, node, allow_value_definitions=True):
        super().load(node)

        valid_symbols = OPTION_SYMBOLS + ["default"]
        if allow_value_definitions:
            valid_symbols += ["values"]

        node.validate_keys(valid_symbols)

        # Allow subclass to define the valid values
        self.values = self.load_valid_values(node)
        if not self.values:
            raise LoadError(
                "{}: No values specified for {} option '{}'".format(
                    node.get_provenance(), self.OPTION_TYPE, self.name
                ),
                LoadErrorReason.INVALID_DATA,
            )

        value_node = node.get_sequence("default", default=[])
        self.value = value_node.as_str_list()
        self.validate(self.value, value_node)

    def load_value(self, node):
        value_node = node.get_sequence(self.name)
        self.value = sorted(value_node.as_str_list())
        self.validate(self.value, value_node)

    def set_value(self, value):
        # Strip out all whitespace, allowing: "value1, value2 , value3"
        stripped = "".join(value.split())

        # Get the comma separated values
        list_value = stripped.split(",")

        self.validate(list_value)
        self.value = sorted(list_value)

    def get_value(self):
        return ",".join(self.value)

    def validate(self, value, node=None):
        for flag in value:
            if flag not in self.values:
                if node is not None:
                    provenance = node.get_provenance()
                    prefix = "{}: ".format(provenance)
                else:
                    prefix = ""
                raise LoadError(
                    "{}Invalid value for flags option '{}': {}\n".format(prefix, self.name, value)
                    + "Valid values: {}".format(", ".join(self.values)),
                    LoadErrorReason.INVALID_DATA,
                )

    def load_valid_values(self, node):
        # Allow the more descriptive error to raise when no values
        # exist rather than bailing out here (by specifying default_value)
        return node.get_str_list("values", default=[])
