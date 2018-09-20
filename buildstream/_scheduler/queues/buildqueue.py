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

from . import Queue, QueueStatus
from ..resources import ResourceType
from ..._platform import Platform


# A queue which assembles elements
#
class BuildQueue(Queue):

    action_name = "Build"
    complete_name = "Built"
    resources = [ResourceType.PROCESS, ResourceType.CACHE]

    def process(self, element):
        return element._assemble()

    def status(self, element):
        # state of dependencies may have changed, recalculate element state
        element._update_state()

        if not element._is_required():
            # Artifact is not currently required but it may be requested later.
            # Keep it in the queue.
            return QueueStatus.WAIT

        if element._cached():
            return QueueStatus.SKIP

        if not element._buildable():
            return QueueStatus.WAIT

        return QueueStatus.READY

    def _check_cache_size(self, job, element, artifact_size):

        # After completing a build job, add the artifact size
        # as returned from Element._assemble() to the estimated
        # artifact cache size
        #
        platform = Platform.get_platform()
        artifacts = platform.artifactcache

        artifacts.add_artifact_size(artifact_size)

        # If the estimated size outgrows the quota, ask the scheduler
        # to queue a job to actually check the real cache size.
        #
        if artifacts.get_quota_exceeded():
            self._scheduler.check_cache_size()

    def done(self, job, element, result, success):

        if success:
            # Inform element in main process that assembly is done
            element._assemble_done()

            # This has to be done after _assemble_done, such that the
            # element may register its cache key as required
            self._check_cache_size(job, element, result)
