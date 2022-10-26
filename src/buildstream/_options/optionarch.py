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
