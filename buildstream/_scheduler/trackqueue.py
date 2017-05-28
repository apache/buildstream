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
#        Jürg Billeter <juerg.billeter@codethink.co.uk>

# System imports
import os

# BuildStream toplevel imports
from .. import Consistency
from ..plugin import _plugin_lookup
from .. import _yaml

# Local imports
from . import Queue, QueueType


# A queue which tracks sources
#
class TrackQueue(Queue):

    action_name = "Track"
    complete_name = "Tracked"
    queue_type = QueueType.FETCH

    def init(self):
        self.changed_sources = []

    def process(self, element):
        return element._track()

    def done(self, element, result, returncode):

        if returncode != 0:
            return

        # Set the new refs in the main process one by one as they complete
        for unique_id, new_ref in result:
            source = _plugin_lookup(unique_id)
            if source._set_ref(new_ref, source._Source__origin_node):

                # Successful update of ref, we're at least resolved now
                self.changed_sources.append(source)
                source._bump_consistency(Consistency.RESOLVED)

                project = source.get_project()
                toplevel = source._Source__origin_toplevel
                filename = source._Source__origin_filename
                fullname = os.path.join(project.element_path, filename)

                # Here we are in master process, what to do if writing
                # to the disk fails for some reason ?
                try:
                    _yaml.dump(toplevel, fullname)
                except OSError as e:
                    source.error("Failed to update project file",
                                 detail="{}: Failed to rewrite tracked source to file {}: {}"
                                 .format(source, fullname, e))
