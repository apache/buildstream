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

import os
import sys
import asyncio
import multiprocessing
import datetime
from collections import deque

from ._message import Message, MessageType
from .exceptions import _ALL_EXCEPTIONS


# Process class that doesn't call waitpid on its own.
# This prevents conflicts with the asyncio child watcher.
class Process(multiprocessing.Process):
    def start(self):
        self._popen = self._Popen(self)
        self._sentinel = self._popen.sentinel


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
#   d.) Fetching results from your queues at queue.results
#
# Args:
#    context: The Context in the parent scheduling process
#    queues: A list of Queues, implemented by the caller
#
class Scheduler():

    def __init__(self, context, queues):
        self.loop = asyncio.get_event_loop()
        self.queues = queues
        self.context = context

        # Attach the queues
        for queue in queues:
            queue.attach(self)

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

        success = True
        for queue in self.queues:
            if queue.failed_elements:
                success = False

        return success

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
            ticking += len(queue.active_jobs)

        if ticking == 0:
            self.loop.stop()


# Queue()
#
# Args:
#    action_name (str): A name for printing status messages about this queue
#    max_jobs (int): Maximum parallel jobs for this queue
#
class Queue():

    def __init__(self, action_name, max_jobs):
        self.action_name = action_name
        self.max_jobs = max_jobs
        self.wait_queue = deque()
        self.done_queue = deque()
        self.scheduler = None
        self.active_jobs = []
        self.failed_elements = []
        self.results = []

    # message()
    #
    # Send a status message to the frontend
    #
    def message(self, plugin, message_type, message, detail=None):

        # Forward this through to the context, if this
        # is in a child process it will be propagated
        # to the parent.
        self.scheduler.context._message(
            Message(plugin._get_unique_id(),
                    message_type,
                    message,
                    detail)
        )

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

    # Attach to the scheduler
    def attach(self, scheduler):
        self.scheduler = scheduler

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

        while len(self.wait_queue) > 0 and len(self.active_jobs) < self.max_jobs:
            element = self.wait_queue.popleft()

            if not self.element_ready(element):
                unready.append(element)
                continue

            job = Job(self.scheduler)
            job.spawn(self.action_name, self.process, self.done, element)
            self.active_jobs.append(job)

        # These were not ready but were in the beginning, give em
        # first priority again next time around
        self.wait_queue.extendleft(unready)

    def done(self, job, returncode, element):
        if returncode == 0:
            self.done_queue.append(element)
        else:
            self.failed_elements.append(element)

        # Get our pipe cleaned once more...
        job.parent_process_queue()
        if job.result:
            self.results.append(job.result)

        self.active_jobs.remove(job)
        self.scheduler.sched()


# Used to distinguish between status messages and return values
class Envelope():
    def __init__(self, message_type, message):
        self.message_type = message_type
        self.message = message


# Job()
#
# Args:
#    scheduler (Scheduler): The scheduler
#
class Job():

    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.queue = multiprocessing.Queue()
        self.process = None
        self.watcher = None
        self.action = None
        self.complete = None
        self.element = None
        self.pid = None
        self.result = None

        # Watch for messages
        scheduler.loop.add_reader(
            self.queue._reader.fileno(),
            self.parent_recv)

    # spawn()
    #
    # Args:
    #    action_name (str): A name to appear in the status messages
    #    action (callable): The action function
    #    complete (callable): The function to call when complete
    #    element (Element): The element to operate on
    #
    def spawn(self, action_name, action, complete, element):
        self.action_name = action_name
        self.action = action
        self.complete = complete
        self.element = element

        # Spawn the process
        self.process = Process(target=self.child_action,
                               args=[element, self.queue])
        self.process.start()
        self.pid = self.process.pid

        # Wait for it to complete
        self.watcher = asyncio.get_child_watcher()
        self.watcher.add_child_handler(self.pid, self.child_complete, element)

    def child_action(self, element, queue):

        # Assign the queue we passed across the process boundaries
        self.queue = queue

        # Set the global message handler in this child
        # process to forward messages to the parent process
        self.scheduler.context._set_message_handler(self.child_send)

        # Time and run the action function
        #
        starttime = datetime.datetime.now()
        try:
            self.message(element, MessageType.START, self.action_name)

            result = self.action(element)
            if result is not None:
                envelope = Envelope('result', result)
                self.queue.put(envelope)

        except _ALL_EXCEPTIONS as e:
            elapsed = datetime.datetime.now() - starttime
            self.message(element, MessageType.FAIL, self.action_name,
                         elapsed=elapsed, detail=str(e))
            self.child_shutdown(1)

        elapsed = datetime.datetime.now() - starttime
        self.message(element, MessageType.SUCCESS, self.action_name, elapsed=elapsed)

        self.child_shutdown(0)

    def child_complete(self, pid, returncode, element):
        self.complete(self, returncode, element)

    def parent_process_envelope(self, envelope):
        if envelope.message_type == 'message':
            # Propagate received messages from children
            # back through the context.
            self.scheduler.context._message(envelope.message)
        elif envelope.message_type == 'result':
            assert(self.result is None)
            self.result = envelope.message
        else:
            raise Exception()

    def parent_process_queue(self):
        while not self.queue.empty():
            envelope = self.queue.get_nowait()
            self.parent_process_envelope(envelope)

    def parent_recv(self, *args):
        self.parent_process_queue()

    def child_shutdown(self, exit_code):
        self.queue.close()
        sys.exit(exit_code)

    def child_send(self, message):
        self.queue.put(Envelope('message', message))

    def message(self, plugin, message_type, message,
                detail=None,
                elapsed=None):
        self.scheduler.context._message(
            Message(plugin._get_unique_id(),
                    message_type,
                    message,
                    detail=detail,
                    elapsed=elapsed)
        )
