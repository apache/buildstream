#
#  Copyright (C) 2016 Codethink Limited
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


class MetaSource():

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
    def __init__(self, element_name, element_index, element_kind, kind, config, directory):
        self.element_name = element_name
        self.element_index = element_index
        self.element_kind = element_kind
        self.kind = kind
        self.config = config
        self.directory = directory
        self.first_pass = False
