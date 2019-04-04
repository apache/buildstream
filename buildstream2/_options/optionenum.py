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


# OptionEnum
#
# An enumeration project option
#
class OptionEnum(Option):

    OPTION_TYPE = 'enum'

    def load(self, node, allow_default_definition=True):
        super(OptionEnum, self).load(node)

        valid_symbols = OPTION_SYMBOLS + ['values']
        if allow_default_definition:
            valid_symbols += ['default']

        _yaml.node_validate(node, valid_symbols)

        self.values = _yaml.node_get(node, list, 'values', default_value=[])
        if not self.values:
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: No values specified for {} option '{}'"
                            .format(_yaml.node_get_provenance(node), self.OPTION_TYPE, self.name))

        # Allow subclass to define the default value
        self.value = self.load_default_value(node)

    def load_value(self, node, *, transform=None):
        self.value = _yaml.node_get(node, str, self.name)
        if transform:
            self.value = transform(self.value)
        self.validate(self.value, _yaml.node_get_provenance(node, self.name))

    def set_value(self, value):
        self.validate(value)
        self.value = value

    def get_value(self):
        return self.value

    def validate(self, value, provenance=None):
        if value not in self.values:
            prefix = ""
            if provenance:
                prefix = "{}: ".format(provenance)
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}Invalid value for {} option '{}': {}\n"
                            .format(prefix, self.OPTION_TYPE, self.name, value) +
                            "Valid values: {}".format(", ".join(self.values)))

    def load_default_value(self, node):
        value = _yaml.node_get(node, str, 'default')
        self.validate(value, _yaml.node_get_provenance(node, 'default'))
        return value
