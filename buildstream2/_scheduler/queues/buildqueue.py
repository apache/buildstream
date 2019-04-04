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
from ..jobs import ElementJob, JobStatus
from ..resources import ResourceType
from ..._message import MessageType


# A queue which assembles elements
#
class BuildQueue(Queue):

    action_name = "Build"
    complete_name = "Built"
    resources = [ResourceType.PROCESS, ResourceType.CACHE]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tried = set()

    def enqueue(self, elts):
        to_queue = []

        for element in elts:
            if not element._cached_failure() or element in self._tried:
                to_queue.append(element)
                continue

            # XXX: Fix this, See https://mail.gnome.org/archives/buildstream-list/2018-September/msg00029.html
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
                             action_cb=self.process,
                             complete_cb=self._job_done,
                             max_retries=self._max_retries)
            self._done_queue.append(element)
            self.failed_elements.append(element)
            self._scheduler._job_complete_callback(job, False)

        return super().enqueue(to_queue)

    def process(self, element):
        return element._assemble()

    def status(self, element):
        if not element._is_required():
            # Artifact is not currently required but it may be requested later.
            # Keep it in the queue.
            return QueueStatus.WAIT

        if element._cached_success():
            return QueueStatus.SKIP

        if not element._buildable():
            return QueueStatus.WAIT

        return QueueStatus.READY

    def _check_cache_size(self, job, element, artifact_size):

        # After completing a build job, add the artifact size
        # as returned from Element._assemble() to the estimated
        # artifact cache size
        #
        context = self._scheduler.context
        artifacts = context.artifactcache

        artifacts.add_artifact_size(artifact_size)

        # If the estimated size outgrows the quota, ask the scheduler
        # to queue a job to actually check the real cache size.
        #
        if artifacts.full():
            self._scheduler.check_cache_size()

    def done(self, job, element, result, status):

        # Inform element in main process that assembly is done
        element._assemble_done()

        # This has to be done after _assemble_done, such that the
        # element may register its cache key as required
        #
        # FIXME: Element._assemble() does not report both the failure state and the
        #        size of the newly cached failed artifact, so we can only adjust the
        #        artifact cache size for a successful build even though we know a
        #        failed build also grows the artifact cache size.
        #
        if status == JobStatus.OK:
            self._check_cache_size(job, element, result)
