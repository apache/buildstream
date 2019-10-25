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
from ..._exceptions import SkipJob


# A queue which pushes element artifacts
#
class ArtifactPushQueue(Queue):

    action_name = "Push"
    complete_name = "Artifacts Pushed"
    resources = [ResourceType.UPLOAD]

    def get_process_func(self):
        return ArtifactPushQueue._push_or_skip

    def status(self, element):
        if element._skip_push():
            return QueueStatus.SKIP

        return QueueStatus.READY

    @staticmethod
    def _push_or_skip(element):
        if not element._push():
            raise SkipJob(ArtifactPushQueue.action_name)
