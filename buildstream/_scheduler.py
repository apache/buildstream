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
import asyncio
import multiprocessing
from collections import deque


# Queue()
#
# Args:
#    max_jobs (int): Maximum parallel jobs for this queue
#
#
class Queue():

    def __init__(self, max_jobs):
        self.count = 0
        self.max_jobs = max_jobs
        self.wait_queue = deque()
        self.done_queue = deque()
        self.rqueue = multiprocessing.Queue()

        # Sneaky set by the scheduler in it's constructor
        self.scheduler = None

    # process()
    #
    # Abstract method for processing an element
    #
    # Args:
    #    element (Element): An element to process
    #
    # Returns:
    #    (any): An optional something to be returned
    #           for every element successfully processed
    #
    #
    def process(self, element):
        pass

    # element_ready()
    #
    # Abstract method for reporting whether an element
    # is ready for processing in this queue or not.
    #
    # Args:
    #    element (Element): An element to process
    #
    # Returns:
    #    (bool): Whether the element is ready for processing
    #
    def element_ready(self, element):
        return True

    # pop_result()
    #
    # Obtain a result in the scheduling process
    # after Scheduler.run() has completed.
    #
    # Returns:
    #   The next result in the queue
    #
    # Results are returned in the order in which
    # their respective elements were processed.
    #
    def pop_result(self):
        if not self.rqueue.empty():
            return self.rqueue.get()
        return None

    def enqueue(self, elts):
        if not elts:
            return
        if isinstance(elts, list):
            self.wait_queue.extend(elts)
        else:
            self.wait_queue.append(elts)

    def dequeue(self):
        while len(self.done_queue) > 0:
            yield self.done_queue.popleft()

    def process_ready(self):
        unready = []

        while len(self.wait_queue) > 0 and self.count < self.max_jobs:
            element = self.wait_queue.popleft()

            if not self.element_ready(element):
                unready.append(element)
                continue

            print('Processing {0} started'.format(element.name))
            run_async(self.do_process, self.done, element, self.rqueue)
            self.count += 1

        # These were not ready but were in the beginning, give em
        # first priority again next time around
        self.wait_queue.extendleft(unready)

    def done(self, pid, returncode, element):
        if returncode == 0:
            print('Processing {0} complete'.format(element.name))
            self.done_queue.append(element)
        else:
            print('Processing {0} failed {1}'.format(element.name, returncode))

        self.count -= 1
        self.scheduler.sched()

    def do_process(self, element, rqueue):
        result = self.process(element)
        if result is not None:
            rqueue.put(result)


# Scheduler()
#
# The scheduler operates on a list queues, each of which is meant to accomplish
# a specific task. Elements enter the first queue when Scheduler.run() is called
# and into the next queue when complete. Scheduler.run() returns when all of the
# elements have been traversed or when an occurs.
#
# Using the scheduler is a matter of:
#   a.) Deriving the Queue class and implementing it's abstract methods
#   b.) Instantiating a Scheduler with one or more queues
#   c.) Calling Scheduler.run(elements) with a list of elements
#   d.) Fetching results from your queues with queue.pop_result()
#
# Args:
#    queues: A list of Queues
#
class Scheduler():

    def __init__(self, queues):
        self.loop = asyncio.get_event_loop()
        self.queues = queues
        self.success = False

        # Set the sneaky backpointer
        for queue in queues:
            queue.scheduler = self

    # run()
    #
    # Args:
    #    plan (list): A list of elements to process
    #    queues (list): A list of Queue objects
    #
    # Returns:
    #    (bool): Whether processing was successful
    #
    # Elements in the 'plan' will be processed by each
    # queue in order. Processing will complete when all
    # elements have been processed by each queue or when
    # an error arises
    #
    def run(self, plan):

        # Append directly into first queue
        self.queues[0].enqueue(list(plan))
        self.sched()
        self.loop.run_forever()
        self.loop.close()

        return self.success

    def sched(self):

        # Pull elements forward through queues
        elements = []
        for queue in self.queues:
            queue.enqueue(elements)
            elements = queue.dequeue()

        # Kickoff whatever processes can be processed at this time
        for queue in self.queues:
            queue.process_ready()

        # If nothings ticking, time to bail out
        ticking = 0
        for queue in self.queues:
            ticking += queue.count
        if ticking == 0:
            self.loop.stop()


# Process class that doesn't call waitpid on its own.
# This prevents conflicts with the asyncio child watcher.
class Process(multiprocessing.Process):
    def start(self):
        self._popen = self._Popen(self)
        self._sentinel = self._popen.sentinel


def run_async(func, cb, arg, rqueue):
    p = Process(target=func, args=[arg, rqueue])
    p.start()
    watcher = asyncio.get_child_watcher()
    watcher.add_child_handler(p.pid, cb, arg)
