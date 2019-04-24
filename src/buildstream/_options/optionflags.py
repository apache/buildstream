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

from .. import _yaml
from .._exceptions import LoadError, LoadErrorReason
from .option import Option, OPTION_SYMBOLS


# OptionFlags
#
# A flags project option
#
class OptionFlags(Option):

    OPTION_TYPE = 'flags'

    def load(self, node, allow_value_definitions=True):
        super(OptionFlags, self).load(node)

        valid_symbols = OPTION_SYMBOLS + ['default']
        if allow_value_definitions:
            valid_symbols += ['values']

        _yaml.node_validate(node, valid_symbols)

        # Allow subclass to define the valid values
        self.values = self.load_valid_values(node)
        if not self.values:
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: No values specified for {} option '{}'"
                            .format(_yaml.node_get_provenance(node), self.OPTION_TYPE, self.name))

        self.value = _yaml.node_get(node, list, 'default', default_value=[])
        self.validate(self.value, _yaml.node_get_provenance(node, 'default'))

    def load_value(self, node, *, transform=None):
        self.value = _yaml.node_get(node, list, self.name)
        if transform:
            self.value = [transform(x) for x in self.value]
        self.value = sorted(self.value)
        self.validate(self.value, _yaml.node_get_provenance(node, self.name))

    def set_value(self, value):
        # Strip out all whitespace, allowing: "value1, value2 , value3"
        stripped = "".join(value.split())

        # Get the comma separated values
        list_value = stripped.split(',')

        self.validate(list_value)
        self.value = sorted(list_value)

    def get_value(self):
        return ",".join(self.value)

    def validate(self, value, provenance=None):
        for flag in value:
            if flag not in self.values:
                prefix = ""
                if provenance:
                    prefix = "{}: ".format(provenance)
                raise LoadError(LoadErrorReason.INVALID_DATA,
                                "{}Invalid value for flags option '{}': {}\n"
                                .format(prefix, self.name, value) +
                                "Valid values: {}".format(", ".join(self.values)))

    def load_valid_values(self, node):
        # Allow the more descriptive error to raise when no values
        # exist rather than bailing out here (by specifying default_value)
        return _yaml.node_get(node, list, 'values', default_value=[])
