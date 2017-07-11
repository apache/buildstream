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

# BuildStream toplevel imports
from .. import Consistency

# Local imports
from . import Queue, QueueType


# A queue which pushes element artifacts
#
class PushQueue(Queue):

    action_name = "Push"
    complete_name = "Pushed"
    queue_type = QueueType.PUSH

    def process(self, element):
        # returns whether an artifact was uploaded or not
        return element._push()

    def skip(self, element):
        return not element._built()

    def done(self, element, result, returncode):

        if returncode != 0:
            return False

        # Element._push() returns True if it uploaded an artifact,
        # here we want to appear skipped if the remote already had
        # the artifact.
        return not result
