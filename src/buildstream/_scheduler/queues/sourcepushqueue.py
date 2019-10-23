#
#  Copyright (C) 2019 Bloomberg Finance LP
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
#        Raoul Hidalgo Charman <raoul.hidalgocharman@codethink.co.uk>

from . import Queue, QueueStatus
from ..resources import ResourceType
from ..._exceptions import SkipJob


# A queue which pushes staged sources
#
class SourcePushQueue(Queue):

    action_name = "Src-push"
    complete_name = "Sources Pushed"
    resources = [ResourceType.UPLOAD]

    def get_process_func(self):
        return SourcePushQueue._push_or_skip

    def status(self, element):
        if element._skip_source_push():
            return QueueStatus.SKIP

        return QueueStatus.READY

    @staticmethod
    def _push_or_skip(element):
        if not element._source_push():
            raise SkipJob(SourcePushQueue.action_name)
