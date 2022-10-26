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


class MetaSource:

    # MetaSource()
    #
    # An abstract object holding data suitable for constructing a Source
    #
    # Args:
    #    element_name: The name of the owning element
    #    element_index: The index of the source in the owning element's source list
    #    element_kind: The kind of the owning element
    #    kind: The kind of the source
    #    config: The configuration data for the source
    #    first_pass: This source will be used with first project pass configuration (used for junctions).
    #
    def __init__(self, element_name, element_index, element_kind, kind, config, directory, first_pass):
        self.element_name = element_name
        self.element_index = element_index
        self.element_kind = element_kind
        self.kind = kind
        self.config = config
        self.directory = directory
        self.first_pass = first_pass
