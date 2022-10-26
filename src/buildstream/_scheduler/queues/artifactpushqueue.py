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

    def __init__(self, scheduler, *, imperative=False, skip_uncached=False):
        super().__init__(scheduler, imperative=imperative)

        self._skip_uncached = skip_uncached

    def get_process_func(self):
        return ArtifactPushQueue._push_or_skip

    def status(self, element):
        if element._skip_push(skip_uncached=self._skip_uncached):
            return QueueStatus.SKIP

        return QueueStatus.READY

    @staticmethod
    def _push_or_skip(element):
        if not element._push():
            raise SkipJob(ArtifactPushQueue.action_name)
