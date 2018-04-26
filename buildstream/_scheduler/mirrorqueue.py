#!/usr/bin/env python3
#
#  Copyright (C) 2018 Codethink Limited
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
#        Valentin David <valentin.david@codethink.co.uk>

from . import Queue, QueueType, QueueStatus


class MirrorQueue(Queue):

    action_name = "Mirror"
    complete_name = "Mirrored"
    queue_type = QueueType.MIRROR

    def process(self, element):
        for source in element.sources():
            source.update_mirror()

    def status(self, element):
        if not list(element.sources()):
            return QueueStatus.SKIP

        return QueueStatus.READY

    def done(self, element, result, success):
        return success
