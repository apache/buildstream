#!/usr/bin/env python3
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
    #    name: The name of the source, for display purposes
    #    kind: The kind of the source
    #    config: The configuration data for the source
    #    origin_node: The original YAML dictionary node defining this source
    #    origin_toplevel: The toplevel YAML loaded from the original file
    #    origin_filename: The filename in which the node was loaded from
    #
    def __init__(self, name, kind, config, directory, origin_node, origin_toplevel, origin_filename):
        self.name = name
        self.kind = kind
        self.config = config
        self.directory = directory
        self.origin_node = origin_node
        self.origin_toplevel = origin_toplevel
        self.origin_filename = origin_filename
