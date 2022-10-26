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
