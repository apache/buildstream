#
#  Copyright (C) 2020 Bloomberg Finance LP
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

from . import Queue, QueueStatus
from ..resources import ResourceType
from ..jobs import JobStatus
from ...types import _KeyStrength


# A queue which queries the cache for artifacts and sources
#
class CacheQueryQueue(Queue):

    action_name = "Cache-query"
    complete_name = "Cache queried"
    resources = [ResourceType.PROCESS, ResourceType.CACHE]

    def __init__(self, scheduler, *, sources=False):
        super().__init__(scheduler)

        self._sources = sources

    def get_process_func(self):
        if not self._sources:
            return CacheQueryQueue._query_artifacts_or_sources
        else:
            return CacheQueryQueue._query_sources

    def status(self, element):
        if not element._get_cache_key(strength=_KeyStrength.WEAK):
            # Strict and weak cache keys are unavailable if the element or
            # a dependency has an unresolved source
            return QueueStatus.SKIP

        return QueueStatus.READY

    def done(self, _, element, result, status):
        if status is JobStatus.FAIL:
            return

        if not self._sources:
            if not element._pull_pending():
                element._load_artifact_done()

    @staticmethod
    def _query_artifacts_or_sources(element):
        element._load_artifact(pull=False)
        if not element._can_query_cache() or not element._cached_success():
            element._query_source_cache()

    @staticmethod
    def _query_sources(element):
        element._query_source_cache()
