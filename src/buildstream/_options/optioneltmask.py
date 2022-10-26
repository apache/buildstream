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

from .. import utils
from .optionflags import OptionFlags


# OptionEltMask
#
# A flags option which automatically only allows element
# names as values.
#
class OptionEltMask(OptionFlags):

    OPTION_TYPE = "element-mask"

    def load(self, node):
        # Ask the parent constructor to disallow value definitions,
        # we define those automatically only.
        super().load_special(node, allow_value_definitions=False)

    # Here we want all valid elements as possible values,
    # but we'll settle for just the relative filenames
    # of files ending with ".bst" in the project element directory
    def load_valid_values(self, node):
        values = []
        for filename in utils.list_relative_paths(self.pool.element_path):
            if filename.endswith(".bst"):
                values.append(filename)
        return values
