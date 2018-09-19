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
class PushQueue(Queue):

    action_name = "Push"
    complete_name = "Pushed"
    resources = [ResourceType.UPLOAD]

    def process(self, element):
        # returns whether an artifact was uploaded or not
        if not element._push():
            raise SkipJob(self.action_name)

    def status(self, element):
        if element._skip_push():
            return QueueStatus.SKIP

        return QueueStatus.READY
