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

from . import Queue, QueueStatus
from ..resources import ResourceType
from ..jobs import JobStatus


# A queue which assembles elements
#
class BuildQueue(Queue):

    action_name = "Build"
    complete_name = "Built"
    resources = [ResourceType.PROCESS, ResourceType.CACHE]

    def get_process_func(self):
        return BuildQueue._assemble_element

    def status(self, element):
        if element._cached_success():
            return QueueStatus.SKIP

        if not element._buildable():
            return QueueStatus.PENDING

        return QueueStatus.READY

    def done(self, job, element, result, status):

        # Inform element in main process that assembly is done
        element._assemble_done(status is JobStatus.OK)

    def register_pending_element(self, element):
        # Set a "buildable" callback for an element not yet ready
        # to be processed in the build queue.
        element._set_buildable_callback(self._enqueue_element)

    @staticmethod
    def _assemble_element(element):
        element._assemble()
