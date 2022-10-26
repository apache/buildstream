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
