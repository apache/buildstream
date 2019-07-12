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

from .._exceptions import LoadError, LoadErrorReason
from .option import Option, OPTION_SYMBOLS


# OptionEnum
#
# An enumeration project option
#
class OptionEnum(Option):

    OPTION_TYPE = 'enum'

    def __init__(self, name, definition, pool):
        self.values = None
        super().__init__(name, definition, pool)

    def load(self, node):
        self.load_special(node)

    def load_special(self, node, allow_default_definition=True):
        super().load(node)

        valid_symbols = OPTION_SYMBOLS + ['values']
        if allow_default_definition:
            valid_symbols += ['default']

        node.validate_keys(valid_symbols)

        self.values = node.get_sequence('values', default=[]).as_str_list()
        if not self.values:
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: No values specified for {} option '{}'"
                            .format(node.get_provenance(), self.OPTION_TYPE, self.name))

        # Allow subclass to define the default value
        self.value = self.load_default_value(node)

    def load_value(self, node, *, transform=None):
        value_node = node.get_scalar(self.name)
        self.value = value_node.as_str()
        if transform:
            self.value = transform(self.value)
        self.validate(self.value, value_node)

    def set_value(self, value):
        self.validate(value)
        self.value = value

    def get_value(self):
        return self.value

    def validate(self, value, node=None):
        if value not in self.values:
            if node is not None:
                provenance = node.get_provenance()
                prefix = "{}: ".format(provenance)
            else:
                prefix = ""
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}Invalid value for {} option '{}': {}\n"
                            .format(prefix, self.OPTION_TYPE, self.name, value) +
                            "Valid values: {}".format(", ".join(self.values)))

    def load_default_value(self, node):
        value_node = node.get_scalar('default')
        value = value_node.as_str()
        self.validate(value, value_node)
        return value
