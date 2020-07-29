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
        return element._assemble()
