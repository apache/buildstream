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
