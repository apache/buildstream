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
        if not element._can_query_cache():
            return QueueStatus.PENDING

        return QueueStatus.READY

    def done(self, _, element, result, status):

        if status is JobStatus.FAIL:
            return

        element._pull_done()

    def register_pending_element(self, element):
        # Set a "can_query_cache"_callback for an element which is not
        # immediately ready to query the artifact cache so that it
        # may be pulled.
        element._set_can_query_cache_callback(self._enqueue_element)

    @staticmethod
    def _pull_or_skip(element):
        if not element._pull():
            raise SkipJob(PullQueue.action_name)

    @staticmethod
    def _check(element):
        if not element._pull(check_remotes=False):
            raise SkipJob(PullQueue.action_name)
