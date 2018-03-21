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
from enum import Enum
import traceback

# Local imports
from .job import Job

# BuildStream toplevel imports
from .._exceptions import BstError, _set_last_task_error
from .._message import Message, MessageType


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


# Queue status for a given element
#
#
class QueueStatus(Enum):
    # The element is waiting for dependencies.
    WAIT = 1

    # The element can skip this queue.
    SKIP = 2

    # The element is ready for processing in this queue.
    READY = 3


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
        self.max_retries = 0

        # For the frontend to know how many elements
        # were successfully processed, failed, or skipped
        # as they did not require processing.
        #
        self.failed_elements = []
        self.processed_elements = []
        self.skipped_elements = []

        # Assert the subclass has setup class data
        assert self.action_name is not None
        assert self.complete_name is not None
        assert self.queue_type is not None

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

    # status()
    #
    # Abstract method for reporting the status of an element.
    #
    # Args:
    #    element (Element): An element to process
    #
    # Returns:
    #    (QueueStatus): The element status
    #
    def status(self, element):
        return QueueStatus.READY

    # prepare()
    #
    # Abstract method for handling job preparation in the main process.
    #
    # Args:
    #    element (Element): The element which is scheduled
    #
    def prepare(self, element):
        pass

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
        if self.queue_type == QueueType.FETCH or self.queue_type == QueueType.PUSH:
            self.max_retries = scheduler.context.sched_network_retries

    def enqueue(self, elts):
        if not elts:
            return

        # Place skipped elements directly on the done queue
        elts = list(elts)
        skip = [elt for elt in elts if self.status(elt) == QueueStatus.SKIP]
        wait = [elt for elt in elts if elt not in skip]

        self.wait_queue.extend(wait)
        self.done_queue.extend(skip)
        self.skipped_elements.extend(skip)

    def dequeue(self):
        while self.done_queue:
            yield self.done_queue.popleft()

    def process_ready(self):
        scheduler = self.scheduler
        unready = []

        while self.wait_queue and scheduler.get_job_token(self.queue_type):
            element = self.wait_queue.popleft()

            status = self.status(element)
            if status == QueueStatus.WAIT:
                scheduler.put_job_token(self.queue_type)
                unready.append(element)
                continue
            elif status == QueueStatus.SKIP:
                scheduler.put_job_token(self.queue_type)
                self.done_queue.append(element)
                self.skipped_elements.append(element)
                continue

            self.prepare(element)

            job = Job(scheduler, element, self.action_name)
            scheduler.job_starting(job)

            job.spawn(self.process, self.job_done, self.max_retries)
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
        try:
            processed = self.done(element, job.result, returncode)

        except BstError as e:

            # Report error and mark as failed
            #
            self.message(element, MessageType.ERROR, "Post processing error", detail=str(e))
            self.failed_elements.append(element)

            # Treat this as a task error as it's related to a task
            # even though it did not occur in the task context
            #
            # This just allows us stronger testing capability
            #
            _set_last_task_error(e.domain, e.reason)

        except Exception as e:   # pylint: disable=broad-except

            # Report unhandled exceptions and mark as failed
            #
            self.message(element, MessageType.BUG,
                         "Unhandled exception in post processing",
                         detail=traceback.format_exc())
            self.failed_elements.append(element)
        else:

            # No exception occured, handle the success/failure state in the normal way
            #
            if returncode == 0:
                self.done_queue.append(element)
                if processed:
                    self.processed_elements.append(element)
                else:
                    self.skipped_elements.append(element)
            else:
                self.failed_elements.append(element)

        # Give the token for this job back to the scheduler
        # immediately before invoking another round of scheduling
        self.scheduler.put_job_token(self.queue_type)

        # Notify frontend
        self.scheduler.job_completed(self, job, returncode == 0)

        self.scheduler.sched()

    # Convenience wrapper for Queue implementations to send
    # a message for the element they are processing
    def message(self, element, message_type, brief, **kwargs):
        context = element._get_context()
        message = Message(element._get_unique_id(), message_type, brief, **kwargs)
        context._message(message)
