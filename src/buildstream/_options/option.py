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

from typing import TYPE_CHECKING

from ..node import _assert_symbol_name

if TYPE_CHECKING:
    from typing import Optional


# Shared symbols for validation purposes
#
OPTION_SYMBOLS = ["type", "description", "variable"]


# Option()
#
# An abstract class representing a project option.
#
# Concrete classes must be created to handle option types,
# the loaded project options is a collection of typed Option
# instances.
#
class Option:

    # Subclasses use this to specify the type name used
    # for the yaml format and error messages
    OPTION_TYPE = None  # type: Optional[str]

    def __init__(self, name, definition, pool):
        self.name = name
        self.variable = None
        self.value = None
        self.pool = pool
        self.load(definition)

    # load()
    #
    # Loads the option attributes from the descriptions
    # in the project.conf
    #
    # Args:
    #    node (dict): The loaded YAML dictionary describing
    #                 the option
    def load(self, node):
        # We don't use the description, but we do require that options have a
        # description.
        node.get_str("description")
        self.variable = node.get_str("variable", default=None)

        # Assert valid symbol name for variable name
        if self.variable is not None:
            _assert_symbol_name(self.variable, "variable name", ref_node=node.get_node("variable"))

    # load_value()
    #
    # Loads the value of the option in string form.
    #
    # Args:
    #    node (Mapping): The YAML loaded key/value dictionary
    #                    to load the value from
    #
    def load_value(self, node):
        pass  # pragma: nocover

    # set_value()
    #
    # Sets the value of an option from a string passed
    # to buildstream on the command line
    #
    # Args:
    #    value (str): The value in string form
    #
    def set_value(self, value):
        pass  # pragma: nocover

    # get_value()
    #
    # Gets the value of an option in string form, this
    # is for the purpose of exporting option values to
    # variables which must be in string form.
    #
    # Returns:
    #    (str): The value in string form
    #
    def get_value(self):
        pass  # pragma: nocover

    # resolve()
    #
    # Called on each option once, after all configuration
    # and cli options have been passed.
    #
    def resolve(self):
        pass  # pragma: nocover
