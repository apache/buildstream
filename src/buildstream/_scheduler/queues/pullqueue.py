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

    def get_process_func(self):
        return PullQueue._pull_or_skip

    def status(self, element):
        if element._pull_pending():
            return QueueStatus.READY
        else:
            return QueueStatus.SKIP

    def done(self, _, element, result, status):

        if status is JobStatus.FAIL:
            return

        element._load_artifact_done()

    @staticmethod
    def _pull_or_skip(element):
        if not element._load_artifact(pull=True):
            raise SkipJob(PullQueue.action_name)
