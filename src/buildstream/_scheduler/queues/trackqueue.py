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

# BuildStream toplevel imports
from ...plugin import Plugin

# Local imports
from . import Queue, QueueStatus
from ..resources import ResourceType
from ..jobs import JobStatus


# A queue which tracks sources
#
class TrackQueue(Queue):

    action_name = "Track"
    complete_name = "Sources Tracked"
    resources = [ResourceType.DOWNLOAD]

    def get_process_func(self):
        return TrackQueue._track_element

    def status(self, element):
        # We can skip elements without any sources
        if not any(element.sources()):

            # But we still have to mark them as tracked
            element._tracking_done()
            return QueueStatus.SKIP

        return QueueStatus.READY

    def done(self, _, element, result, status):

        if status is JobStatus.FAIL:
            return

        # Set the new refs in the main process one by one as they complete,
        # writing to bst files this time
        if result is not None:
            for unique_id, new_ref, ref_changed in result:
                if ref_changed:
                    source = Plugin._lookup(unique_id)
                    source._set_ref(new_ref, save=True)

        element._tracking_done()

    @staticmethod
    def _track_element(element):
        return element._track()
