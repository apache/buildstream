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
from ... import Consistency

# Local imports
from . import Queue, QueueStatus
from ..resources import ResourceType


# A queue which fetches element sources
#
class FetchQueue(Queue):

    action_name = "Fetch"
    complete_name = "Fetched"
    resources = [ResourceType.DOWNLOAD]

    def __init__(self, scheduler, skip_cached=False):
        super().__init__(scheduler)

        self._skip_cached = skip_cached

    def process(self, element):
        for source in element.sources():
            source._fetch()

    def status(self, element):
        # state of dependencies may have changed, recalculate element state
        element._update_state()

        if not element._is_required():
            # Artifact is not currently required but it may be requested later.
            # Keep it in the queue.
            return QueueStatus.WAIT

        # Optionally skip elements that are already in the artifact cache
        if self._skip_cached:
            if not element._can_query_cache():
                return QueueStatus.WAIT

            if element._cached():
                return QueueStatus.SKIP

        # This will automatically skip elements which
        # have no sources.
        if element._get_consistency() == Consistency.CACHED:
            return QueueStatus.SKIP

        return QueueStatus.READY

    def done(self, _, element, result, success):

        if not success:
            return

        element._update_state()

        # Successful fetch, we must be CACHED now
        assert element._get_consistency() == Consistency.CACHED
