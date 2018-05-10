#!/usr/bin/env python3
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

from . import Queue, QueueStatus, QueueType


# A queue which assembles elements
#
class BuildQueue(Queue):

    action_name = "Build"
    complete_name = "Built"
    queue_type = QueueType.BUILD

    def process(self, element):
        element._assemble()
        return element._get_unique_id()

    def status(self, element):
        # state of dependencies may have changed, recalculate element state
        element._update_state()

        if not element._is_required():
            # Artifact is not currently required but it may be requested later.
            # Keep it in the queue.
            return QueueStatus.WAIT

        if element._cached():
            return QueueStatus.SKIP

        if not element._buildable():
            return QueueStatus.WAIT

        return QueueStatus.READY

    def done(self, element, result, success):

        if success:
            # Inform element in main process that assembly is done
            element._assemble_done()

        return True
