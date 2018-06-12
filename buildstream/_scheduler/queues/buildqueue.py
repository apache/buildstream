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

from datetime import timedelta

from . import Queue, QueueStatus
from ..jobs import ElementJob
from ..resources import ResourceType
from ..._message import MessageType


# A queue which assembles elements
#
class BuildQueue(Queue):

    action_name = "Build"
    complete_name = "Built"
    resources = [ResourceType.PROCESS]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tried = set()

    def enqueue(self, elts):
        to_queue = []

        for element in elts:
            if not element._cached_failure() or element in self._tried:
                to_queue.append(element)
                continue

            # Bypass queue processing entirely the first time it's tried.
            self._tried.add(element)
            _, description, detail = element._get_build_result()
            logfile = element._get_build_log()
            self._message(element, MessageType.FAIL, description,
                          detail=detail, action_name=self.action_name,
                          elapsed=timedelta(seconds=0),
                          logfile=logfile)
            job = ElementJob(self._scheduler, self.action_name,
                             logfile, element=element, queue=self,
                             resources=self.resources,
                             action_cb=self.process,
                             complete_cb=self._job_done,
                             max_retries=self._max_retries)
            self._done_queue.append(job)
            self.failed_elements.append(element)
            self._scheduler._job_complete_callback(job, False)

        return super().enqueue(to_queue)

    def process(self, element):
        element._assemble()
        return element._get_unique_id()

    def status(self, element):
        # state of dependencies may have changed, recalculate element state
        element._update_state()

        if not element._is_required():
            # Artifact is not currently required but it may be requested later.
            # Keep it in the queue.
            return QueueStatus.WAIT

        if element._cached_success():
            return QueueStatus.SKIP

        if not element._buildable():
            return QueueStatus.WAIT

        return QueueStatus.READY

    def _check_cache_size(self, job, element):
        if not job.child_data:
            return

        artifact_size = job.child_data.get('artifact_size', False)

        if artifact_size:
            cache = element._get_artifact_cache()
            cache._add_artifact_size(artifact_size)

            if cache.get_approximate_cache_size() > self._scheduler.context.cache_quota:
                self._scheduler._check_cache_size_real()

    def done(self, job, element, result, success):

        if success:
            # Inform element in main process that assembly is done
            element._assemble_done()

        # This has to be done after _assemble_done, such that the
        # element may register its cache key as required
        self._check_cache_size(job, element)

        return True
