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
from ruamel import yaml

from ._message import Message, MessageType, unconditional_messages
from .exceptions import _BstError
from .plugin import _plugin_lookup
from . import utils


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
#   a.) Deriving the Queue class and implementing its abstract methods
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

        return not self.failed_elements()

    def failed_elements(self):
        failed = False
        for queue in self.queues:
            if queue.failed_elements:
                failed = True
                break
        return failed

    def sched(self):

        queue_jobs = True

        # Stop queuing jobs when there is an error
        if self.failed_elements():
            if self.context.sched_error_action == 'quit':
                queue_jobs = False

        if queue_jobs:

            # Pull elements forward through queues
            elements = []
            for queue in self.queues:
                # Enqueue elements complete from the last queue
                queue.enqueue(elements)

                # Dequeue processed elements for the next queue
                elements = list(queue.dequeue())
                elements = list(elements)

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

        # Subclass initializer
        self.init()

    #####################################################
    #     Abstract Methods for Queue implementations    #
    #####################################################

    # init()
    #
    # Initialize the queue, instead of overriding constructor.
    #
    def init(self):
        pass

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

    def dequeue(self):
        while len(self.done_queue) > 0:
            yield self.done_queue.popleft()

    def process_ready(self):
        unready = []

        while len(self.wait_queue) > 0 and len(self.active_jobs) < self.max_jobs:
            element = self.wait_queue.popleft()

            if not self.ready(element):
                unready.append(element)
                continue

            job = Job(self.scheduler, self.action_name)
            job.spawn(self.action_name, self.process, self.job_done, element)
            self.active_jobs.append(job)

        # These were not ready but were in the beginning, give em
        # first priority again next time around
        self.wait_queue.extendleft(unready)

    def job_done(self, job, returncode, element):
        if returncode == 0:
            self.done_queue.append(element)
        else:
            self.failed_elements.append(element)

        job.parent_process_queue()
        self.active_jobs.remove(job)

        # Give the result of the job to the Queue implementor
        self.done(element, job.result, returncode)

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
#    action_name (str): The queue action name
#
class Job():

    def __init__(self, scheduler, action_name):

        # Shared with child process
        self.scheduler = scheduler            # The scheduler
        self.queue = multiprocessing.Queue()  # A message passing queue
        self.process = None                   # The Process object
        self.watcher = None                   # Child process watcher
        self.parent_action = action_name      # The action name for the Queue
        self.action = None                    # The action callable function
        self.complete = None                  # The complete callable function
        self.element = None                   # The element we're processing

        # Only relevant in parent process after spawning
        self.pid = None                       # The child's pid in the parent
        self.result = None                    # Return value of child action in the parent

        self.parent_listen()

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
                               args=[element, self.queue, self.parent_action])
        self.process.start()
        self.pid = self.process.pid

        # Wait for it to complete
        self.watcher = asyncio.get_child_watcher()
        self.watcher.add_child_handler(self.pid, self.child_complete, element)

    # Local message wrapper
    def message(self, plugin, message_type, message, **kwargs):
        args = dict(kwargs)
        args['scheduler'] = True
        self.scheduler.context._message(
            Message(plugin._get_unique_id(),
                    message_type,
                    message,
                    **args))

    #######################################################
    #                  Child Process                      #
    #######################################################
    def child_action(self, element, queue, action_name):

        # Assign the queue we passed across the process boundaries
        #
        # Set the global message handler in this child
        # process to forward messages to the parent process
        self.queue = queue
        self.scheduler.context._set_message_handler(self.child_message_handler)

        # Time, log and and run the action function
        #
        with element._logging_enabled(action_name) as filename:
            starttime = datetime.datetime.now()
            self.message(element, MessageType.START, self.action_name,
                         logfile=filename)

            # Print the element's environment at the beginning of any element's log file.
            #
            # This should probably be omitted for non-build tasks but it's harmless here
            elt_env = utils._node_sanitize(element._Element__environment)
            env_dump = yaml.round_trip_dump(elt_env, default_flow_style=False, allow_unicode=True)
            self.message(element, MessageType.LOG,
                         "Build environment for element {}".format(element._get_display_name()),
                         detail=env_dump, logfile=filename)

            try:
                result = self.action(element)
                if result is not None:
                    envelope = Envelope('result', result)
                    self.queue.put(envelope)

            except _BstError as e:
                elapsed = datetime.datetime.now() - starttime
                self.message(element, MessageType.FAIL, self.action_name,
                             elapsed=elapsed, detail=str(e),
                             logfile=filename, sandbox=e.sandbox)
                self.child_shutdown(1)

            elapsed = datetime.datetime.now() - starttime
            self.message(element, MessageType.SUCCESS, self.action_name, elapsed=elapsed,
                         logfile=filename)

            self.child_shutdown(0)

    def child_complete(self, pid, returncode, element):
        self.complete(self, returncode, element)

    def child_shutdown(self, exit_code):
        self.queue.close()
        sys.exit(exit_code)

    def child_log(self, plugin, message, context):

        with plugin._output_file() as output:
            INDENT = "    "
            EMPTYTIME = "--:--:--"

            name = '[' + plugin._get_display_name() + ']'

            fmt = "[{timecode: <8}] {type: <7} {name: <15}: {message}"
            detail = ''
            if message.detail is not None:
                fmt += "\n\n{detail}"
                detail = message.detail.rstrip('\n')
                detail = INDENT + INDENT.join(detail.splitlines(True))

            timecode = EMPTYTIME
            if message.message_type in (MessageType.SUCCESS, MessageType.FAIL):
                hours, remainder = divmod(int(message.elapsed.total_seconds()), 60 * 60)
                minutes, seconds = divmod(remainder, 60)
                timecode = "{0:02d}:{1:02d}:{2:02d}".format(hours, minutes, seconds)

            message_text = fmt.format(timecode=timecode,
                                      type=message.message_type.upper(),
                                      name=name,
                                      message=message.message,
                                      detail=detail)

            output.write('{}\n'.format(message_text))
            output.flush()

    def child_message_handler(self, message, context):
        plugin = _plugin_lookup(message.unique_id)

        # Tag them on the way out the door...
        message.action_name = self.parent_action

        # Log first
        self.child_log(plugin, message, context)

        # Send to frontend if appropriate
        if (context._silent_messages() and
            message.message_type not in unconditional_messages):
            return

        if message.message_type == MessageType.LOG:
            return

        self.queue.put(Envelope('message', message))

    #######################################################
    #                 Parent Process                      #
    #######################################################
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

    def parent_listen(self):
        # Warning: Platform specific code up ahead
        #
        #   The multiprocessing.Queue object does not tell us how
        #   to receive io events in the receiving process, so we
        #   need to sneak in and get its file descriptor.
        #
        #   The _reader member of the Queue is currently private
        #   but well known, perhaps it will become public:
        #
        #      http://bugs.python.org/issue3831
        #
        self.scheduler.loop.add_reader(
            self.queue._reader.fileno(), self.parent_recv)
