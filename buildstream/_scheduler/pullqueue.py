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

# Local imports
from . import Queue, QueueType


# A queue which pulls element artifacts
#
class PullQueue(Queue):

    action_name = "Pull"
    complete_name = "Pulled"
    queue_type = QueueType.FETCH

    def process(self, element):
        # returns whether an artifact was downloaded or not
        return element._pull()

    def skip(self, element):
        return element._cached()

    def done(self, element, result, returncode):

        if returncode != 0:
            return False

        # return code is 0 even if artifact was unavailable
        element._cached(recalculate=True)

        # Element._pull() returns True if it downloaded an artifact,
        # here we want to appear skipped if we did not download.
        return not result
