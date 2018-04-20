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
#  Author:
#        Tristan Daniël Maat <tristan.maat@codethink.co.uk>
#
from itertools import chain


# QueueRunner()
#
# The queue runner manages queues and determines what jobs should be
# run at any given point.
#
# `QueueRunner.schedule_jobs` will pull elements through queues as
# appropriate, and return jobs for any "ready" elements to submit for
# processing.
#
# Args:
#     scheduler (Scheduler) - The scheduler to provide jobs for.
#     queues ([Queue]) - The queues to manage.
#
class QueueRunner():
    def __init__(self, scheduler, queues=None):
        try:
            queues = list(queues)
        except TypeError:
            queues = [queues] if queues is not None else []

        self.queues = queues
        self._scheduler = scheduler

    # append()
    #
    # Append a queue to the list of queues.
    #
    # Args:
    #     queue (Queue) - The queue to append
    #
    def append(self, queue):
        self.queues.append(queue)

    # extend()
    #
    # Extend the list of queues.
    #
    # Args:
    #    queues (typing.Iterable[Queue]) - The queues to append
    #
    def extend(self, queues):
        self.queues.extend(queues)

    # schedule_jobs()
    #
    # Pull elements through the managed queues, and collect jobs to be
    # executed by the scheduler
    #
    # Returns:
    #    (typing.List[Job]) jobs for the scheduler to execute.
    #
    def schedule_jobs(self):

        ready = []
        process_queues = True

        while self._scheduler._queue_jobs and process_queues:

            # Pull elements forward through queues
            elements = []
            for queue in self.queues:
                # Enqueue elements complete from the last queue
                queue.enqueue(elements)

                # Dequeue processed elements for the next queue
                elements = list(queue.dequeue())

            # Kickoff whatever processes can be processed at this time
            #
            # We start by queuing from the last queue first, because we want to
            # give priority to queues later in the scheduling process in the case
            # that multiple queues share the same token type.
            #
            # This avoids starvation situations where we dont move on to fetch
            # tasks for elements which failed to pull, and thus need all the pulls
            # to complete before ever starting a build
            ready.extend(chain.from_iterable(queue.process_ready() for queue in reversed(self.queues)))

            # process_ready() may have skipped jobs, adding them to the done_queue.
            # Pull these skipped elements forward to the next queue and process them.
            process_queues = any(q.dequeue_ready() for q in self.queues)

        return ready
