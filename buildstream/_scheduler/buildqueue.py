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

from . import Queue, QueueType


# A queue which assembles elements
#
class BuildQueue(Queue):

    action_name = "Build"
    complete_name = "Built"
    queue_type = QueueType.BUILD

    def process(self, element):
        element._assemble()
        return element._get_unique_id()

    def ready(self, element):
        return element._buildable()

    def skip(self, element):
        return element._cached()

    def done(self, element, result, returncode):
        # Elements are cached after they are successfully assembled
        if returncode == 0:
            element._cached(recalculate=True)
            element._set_built()

        return True
