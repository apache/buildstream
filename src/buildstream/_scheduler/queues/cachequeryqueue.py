#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

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

    def __init__(self, scheduler, *, sources=False, sources_if_cached=False):
        super().__init__(scheduler)

        self._sources = sources
        self._sources_if_cached = sources_if_cached

    def get_process_func(self):
        if self._sources_if_cached:
            return CacheQueryQueue._query_artifacts_and_sources
        elif not self._sources:
            return CacheQueryQueue._query_artifacts_or_sources
        else:
            return CacheQueryQueue._query_sources

    def status(self, element):
        if element._can_query_cache():
            # Cache status already available.
            # This is the case for artifact elements, which load the
            # artifact early on.
            return QueueStatus.SKIP

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
    def _query_artifacts_and_sources(element):
        element._load_artifact(pull=False)
        element._query_source_cache()

    @staticmethod
    def _query_sources(element):
        element._query_source_cache()
