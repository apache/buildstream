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
#        Raoul Hidalgo Charman <raoul.hidalgocharman@codethink.co.uk>

import platform
from .optionenum import OptionEnum


# OptionOS
#
class OptionOS(OptionEnum):

    OPTION_TYPE = "os"

    def load(self, node):
        super().load_special(node, allow_default_definition=False)

    def load_default_value(self, node):
        return platform.uname().system

    def resolve(self):

        # Validate that the default OS reported by uname() is explicitly
        # supported by the project, if not overridden by user config or cli.
        self.validate(self.value)
