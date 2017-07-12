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

# System imports
from collections import deque

# Local imports
from .job import Job


# Indicates the kind of activity
#
#
class QueueType():
    # Tasks which download stuff from the internet
    FETCH = 1

    # CPU/Disk intensive tasks
    BUILD = 2

    # Tasks which upload stuff to the internet
    PUSH = 3


# Queue()
#
#
class Queue():

    # These should be overridden on class data of of concrete Queue implementations
    action_name = None
    complete_name = None
    queue_type = None

    def __init__(self):
        self.scheduler = None
        self.wait_queue = deque()
        self.done_queue = deque()
        self.active_jobs = []

        # For the frontend to know how many elements
        # were successfully processed, failed, or skipped
        # as they did not require processing.
        #
        self.failed_elements = []
        self.processed_elements = []
        self.skipped_elements = []

        # Assert the subclass has setup class data
        assert(self.action_name is not None)
        assert(self.complete_name is not None)
        assert(self.queue_type is not None)

    #####################################################
    #     Abstract Methods for Queue implementations    #
    #####################################################

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

    # ready()
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
    def ready(self, element):
        return True

    # skip()
    #
    # Abstract method for reporting whether an element
    # can be skipped for this phase.
    #
    # Args:
    #    element (Element): An element to process
    #
    # Returns:
    #    (bool): Whether the element can be skipped
    #
    def skip(self, element):
        return False

    # done()
    #
    # Abstract method for handling a successful job completion.
    #
    # Args:
    #    element (Element): The element which completed processing
    #    result (any): The return value of the process() implementation
    #    returncode (int): The process return code, 0 = success
    #
    # Returns:
    #    (bool): True if the element should appear to be processsed,
    #            Otherwise False will count the element as "skipped"
    #
    def done(self, element, result, returncode):
        pass

    #####################################################
    #     Queue internals and Scheduler facing APIs     #
    #####################################################

    # Attach to the scheduler
    def attach(self, scheduler):
        self.scheduler = scheduler

    def enqueue(self, elts):
        if not elts:
            return

        # Place skipped elements directly on the done queue
        elts = list(elts)
        skip = [elt for elt in elts if self.skip(elt)]
        wait = [elt for elt in elts if elt not in skip]

        self.wait_queue.extend(wait)
        self.done_queue.extend(skip)
        self.skipped_elements.extend(skip)

    def dequeue(self):
        while len(self.done_queue) > 0:
            yield self.done_queue.popleft()

    def process_ready(self):
        scheduler = self.scheduler
        unready = []

        while len(self.wait_queue) > 0 and scheduler.get_job_token(self.queue_type):
            element = self.wait_queue.popleft()

            if not self.ready(element):
                scheduler.put_job_token(self.queue_type)
                unready.append(element)
                continue
            elif self.skip(element):
                scheduler.put_job_token(self.queue_type)
                self.done_queue.append(element)
                self.skipped_elements.append(element)
                continue

            job = Job(scheduler, element, self.action_name)
            scheduler.job_starting(job)

            job.spawn(self.process, self.job_done)
            self.active_jobs.append(job)

        # These were not ready but were in the beginning, give em
        # first priority again next time around
        self.wait_queue.extendleft(unready)

    def job_done(self, job, returncode, element):

        # Shutdown the job
        job.shutdown()
        self.active_jobs.remove(job)

        # Give the result of the job to the Queue implementor,
        # and determine if it should be considered as processed
        # or skipped.
        if self.done(element, job.result, returncode):
            skip = False
        else:
            skip = True

        if returncode == 0:
            self.done_queue.append(element)
            if skip:
                self.skipped_elements.append(element)
            else:
                self.processed_elements.append(element)
        else:
            self.failed_elements.append(element)

        # Notify frontend
        self.scheduler.job_completed(job, returncode == 0)

        # Give the token for this job back to the scheduler
        # immediately before invoking another round of scheduling
        self.scheduler.put_job_token(self.queue_type)
        self.scheduler.sched()
