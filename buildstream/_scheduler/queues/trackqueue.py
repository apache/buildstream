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

# BuildStream toplevel imports
from ...plugin import _plugin_lookup
from ... import SourceError

# Local imports
from . import Queue, QueueStatus
from ..resources import ResourceType


# A queue which tracks sources
#
class TrackQueue(Queue):

    action_name = "Track"
    complete_name = "Tracked"
    resources = [ResourceType.DOWNLOAD]

    def process(self, element):
        return element._track()

    def status(self, element):
        # We can skip elements entirely if they have no sources.
        if not list(element.sources()):

            # But we still have to mark them as tracked
            element._tracking_done()
            return QueueStatus.SKIP

        return QueueStatus.READY

    def done(self, _, element, result, success):

        if not success:
            return

        # Set the new refs in the main process one by one as they complete
        for unique_id, new_ref in result:
            source = _plugin_lookup(unique_id)
            source._save_ref(new_ref)

        element._tracking_done()
