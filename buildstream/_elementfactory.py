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

from ._plugincontext import _PluginContext
from .config import _site_info
from .element import Element

# A ElementFactory creates Element instances
# in the context of a given factory
#
# Args:
#     plugin_base (PluginBase): The main PluginBase object to work with
#     searchpath (list):        A list of external paths to search for Element plugins
#
class _ElementFactory(_PluginContext):

    def __init__(self, plugin_base, searchpath=None):

        if searchpath is None:
            searchpath = []
        
        searchpath.insert(0, _site_info['element_plugins'])
        super().__init__(plugin_base, Element, searchpath)

    # create():
    #
    # Create an Element object, the pipeline uses this to create Element
    # objects on demand for a given pipeline.
    #
    # Args:
    #     kind (str): The kind of Element to create
    #
    # Returns: A newly created Element object of the appropriate kind
    #
    # Raises: PluginError
    #
    def create(self, kind):
        element_type = self.lookup(kind)
        return element_type()
