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

# Local imports
from . import Queue, QueueStatus
from ..resources import ResourceType
from ..jobs import JobStatus


# A queue which fetches element sources
#
class FetchQueue(Queue):

    action_name = "Fetch"
    complete_name = "Sources Fetched"
    resources = [ResourceType.DOWNLOAD]

    def __init__(self, scheduler, skip_cached=False, fetch_original=False):
        super().__init__(scheduler)

        self._skip_cached = skip_cached
        self._should_fetch_original = fetch_original

    def get_process_func(self):
        if self._should_fetch_original:
            return FetchQueue._fetch_original
        else:
            return FetchQueue._fetch_not_original

    def status(self, element):
        # Optionally skip elements that are already in the artifact cache
        if self._skip_cached:
            if not element._can_query_cache():
                return QueueStatus.PENDING

            if element._cached():
                return QueueStatus.SKIP

        # This will automatically skip elements which
        # have no sources.

        if not element._should_fetch(self._should_fetch_original):
            return QueueStatus.SKIP

        return QueueStatus.READY

    def done(self, _, element, result, status):

        if status is JobStatus.FAIL:
            return

        element._fetch_done(self._should_fetch_original)

    def register_pending_element(self, element):
        # Set a "can_query_cache" callback for an element not yet ready
        # to be processed in the fetch queue.
        element._set_can_query_cache_callback(self._enqueue_element)

    @staticmethod
    def _fetch_not_original(element):
        element._fetch(fetch_original=False)

    @staticmethod
    def _fetch_original(element):
        element._fetch(fetch_original=True)
