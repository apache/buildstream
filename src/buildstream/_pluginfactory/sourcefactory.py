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

from .pluginfactory import PluginFactory
from .pluginorigin import PluginType

# A SourceFactory creates Source instances
# in the context of a given factory
#
# Args:
#     plugin_base (PluginBase): The main PluginBase object to work with
#
class SourceFactory(PluginFactory):
    def __init__(self, plugin_base):
        super().__init__(plugin_base, PluginType.SOURCE)

    # create():
    #
    # Create a Source object, the pipeline uses this to create Source
    # objects on demand for a given pipeline.
    #
    # Args:
    #    context (object): The Context object for processing
    #    project (object): The project object
    #    meta (object): The loaded MetaSource
    #    variables (Variables): The variables available to the source
    #
    # Returns:
    #    A newly created Source object of the appropriate kind
    #
    # Raises:
    #    PluginError (if the kind lookup failed)
    #    LoadError (if the source itself took issue with the config)
    #
    def create(self, context, project, meta, variables):
        source_type, _ = self.lookup(context.messenger, meta.kind, meta.provenance)
        source = source_type(context, project, meta, variables)
        return source
