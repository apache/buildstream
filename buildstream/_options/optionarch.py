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

import os
from .optionenum import OptionEnum


# OptionArch
#
# An enumeration project option which does not allow
# definition of a default value, but instead tries to set
# the default value to the machine architecture introspected
# using `uname`
#
# Note that when using OptionArch in a project, it will automatically
# bail out of the host machine `uname` reports a machine architecture
# not supported by the project, in the case that no option was
# specifically specified
#
class OptionArch(OptionEnum):

    OPTION_TYPE = 'arch'

    def load(self, node):
        super(OptionArch, self).load(node, allow_default_definition=False)

    def load_default_value(self, node):
        _, _, _, _, machine_arch = os.uname()
        return machine_arch

    def resolve(self):

        # Validate that the default machine arch reported by uname() is
        # explicitly supported by the project, only if it was not
        # overridden by user configuration or cli.
        #
        # If the value is specified on the cli or user configuration,
        # then it will already be valid.
        #
        self.validate(self.value)
