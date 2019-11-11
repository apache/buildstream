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
