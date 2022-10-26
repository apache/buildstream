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
