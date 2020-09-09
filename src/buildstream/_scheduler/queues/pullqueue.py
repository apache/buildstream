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
from ..._exceptions import SkipJob
from ...types import _KeyStrength


# A queue which pulls element artifacts
#
class PullQueue(Queue):

    action_name = "Pull"
    complete_name = "Artifacts Pulled"
    resources = [ResourceType.DOWNLOAD, ResourceType.CACHE]

    def __init__(self, scheduler, *, check_remotes=True):
        super().__init__(scheduler)

        self._check_remotes = check_remotes

    def get_process_func(self):
        if self._check_remotes:
            return PullQueue._pull_or_skip
        else:
            return PullQueue._check

    def status(self, element):
        if not element._get_cache_key(strength=_KeyStrength.WEAK):
            # Strict and weak cache keys are unavailable if the element or
            # a dependency has an unresolved source
            return QueueStatus.SKIP

        return QueueStatus.READY

    def done(self, _, element, result, status):

        if status is JobStatus.FAIL:
            return

        artifact = element._temp_job_result
        element._temp_job_result = None

        element._pull_done(artifact)

    @staticmethod
    def _pull_or_skip(element):
        artifact = element._pull()
        element._temp_job_result = artifact
        if not artifact.cached():
            raise SkipJob(PullQueue.action_name)

    @staticmethod
    def _check(element):
        artifact = element._pull(check_remotes=False)
        element._temp_job_result = artifact
        if not artifact.cached():
            raise SkipJob(PullQueue.action_name)
