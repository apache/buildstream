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

from .._exceptions import LoadError, PlatformError
from ..exceptions import LoadErrorReason
from .._platform import Platform
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

    OPTION_TYPE = "arch"

    def load(self, node):
        super().load_special(node, allow_default_definition=False)

    def load_default_value(self, node):
        arch = Platform.get_host_arch()

        default_value = None

        for index, value in enumerate(self.values):
            try:
                canonical_value = Platform.canonicalize_arch(value)
                if default_value is None and canonical_value == arch:
                    default_value = value
                    # Do not terminate the loop early to ensure we validate
                    # all values in the list.
            except PlatformError as e:
                provenance = node.get_sequence("values").scalar_at(index).get_provenance()
                prefix = ""
                if provenance:
                    prefix = "{}: ".format(provenance)
                raise LoadError(
                    "{}Invalid value for {} option '{}': {}".format(prefix, self.OPTION_TYPE, self.name, e),
                    LoadErrorReason.INVALID_DATA,
                )

        if default_value is None:
            # Host architecture is not supported by the project.
            # Do not raise an error here as the user may override it.
            # If the user does not override it, an error will be raised
            # by resolve()/validate().
            default_value = arch

        return default_value

    def resolve(self):

        # Validate that the default machine arch reported by uname() is
        # explicitly supported by the project, only if it was not
        # overridden by user configuration or cli.
        #
        # If the value is specified on the cli or user configuration,
        # then it will already be valid.
        #
        self.validate(self.value)
