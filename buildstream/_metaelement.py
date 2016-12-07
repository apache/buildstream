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


class MetaElement():

    # MetaElement()
    #
    # An abstract object holding data suitable for constructing an Element
    #
    # Args:
    #    name: The resolved element name
    #    kind: The element kind
    #    sources: An array of MetaSource objects
    #    config: The configuration data for the element
    #
    def __init__(self, name, kind, sources, config):
        self.name = name
        self.kind = kind
        self.sources = sources
        self.config = config

        self.build_dependencies = []
        self.dependencies = []
