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
import os
import asyncio
import signal
import datetime

# Local imports
from .queue import Queue, QueueType

# BuildStream toplevel imports
from .. import _signals


# A decent return code for Scheduler.run()
class SchedStatus():
    SUCCESS = 0
    ERROR = -1
    TERMINATED = 1


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
#   d.) Fetching results from your queues
#
# Args:
#    context: The Context in the parent scheduling process
#    interrupt_callback: A callback to handle ^C
#    ticker_callback: A callback call once per second
#    job_start_callback: A callback call when each job starts
#    job_complete_callback: A callback call when each job completes
#
class Scheduler():

    def __init__(self, context,
                 interrupt_callback=None,
                 ticker_callback=None,
                 job_start_callback=None,
                 job_complete_callback=None):
        self.loop = None
        self.interrupt_callback = interrupt_callback
        self.ticker_callback = ticker_callback
        self.job_start_callback = job_start_callback
        self.job_complete_callback = job_complete_callback
        self.context = context
        self.queues = None
        self.starttime = None
        self.suspendtime = None

        # Initialize task tokens with the number allowed by
        # the user configuration
        self.job_tokens = {
            QueueType.FETCH: context.sched_fetchers,
            QueueType.BUILD: context.sched_builders
        }

        # Some local state
        self.queue_jobs = True      # Whether we should continue to queue jobs
        self.terminated = False     # Hold on to whether we were terminated
        self.suspended = False      # Whether tasks are currently suspended
        self.internal_stops = 0     # Amount of SIGSTP signals we've introduced (handle feedback)

    # run()
    #
    # Args:
    #    queues (list): A list of Queue objects
    #
    # Returns:
    #    (SchedStatus): How the scheduling terminated
    #
    # Elements in the 'plan' will be processed by each
    # queue in order. Processing will complete when all
    # elements have been processed by each queue or when
    # an error arises
    #
    def run(self, queues):

        self.starttime = datetime.datetime.now()

        # Attach the queues
        self.queues = queues
        for queue in queues:
            queue.attach(self)

        self.loop = asyncio.get_event_loop()

        # Add timeouts
        if self.ticker_callback:
            self.loop.call_later(1, self.tick)

        # Handle unix signals while running
        self.connect_signals()

        # Run the queues
        self.sched()
        self.loop.run_forever()
        self.loop.close()

        # Stop handling unix signals
        self.disconnect_signals()

        failed = self.failed_elements()
        self.queues = None
        self.loop = None

        if failed:
            status = SchedStatus.ERROR
        elif self.terminated:
            status = SchedStatus.TERMINATED
        else:
            status = SchedStatus.SUCCESS

        return self.elapsed_time(), status

    # terminate_jobs()
    #
    # Forcefully terminates all ongoing jobs.
    #
    def terminate_jobs(self):
        wait_start = datetime.datetime.now()
        wait_limit = 10.0

        with _signals.blocked([signal.SIGINT]):

            # First tell all jobs to terminate
            for queue in self.queues:
                for job in queue.active_jobs:
                    job.terminate()

            # Now wait for them to really terminate
            for queue in self.queues:
                for job in queue.active_jobs:
                    elapsed = datetime.datetime.now() - wait_start
                    timeout = max(wait_limit - elapsed.total_seconds(), 0.0)
                    job.terminate_wait(timeout)

            self.loop.stop()
            self.terminated = True

    # suspend_jobs()
    #
    # Suspend all ongoing jobs.
    #
    def suspend_jobs(self):
        if not self.suspended:
            self.suspendtime = datetime.datetime.now()
            self.suspended = True
            for queue in self.queues:
                for job in queue.active_jobs:
                    job.suspend()

    # resume_jobs()
    #
    # Resume suspended jobs.
    #
    def resume_jobs(self):
        if self.suspended:
            for queue in self.queues:
                for job in queue.active_jobs:
                    job.resume()
            self.suspended = False
            self.starttime += (datetime.datetime.now() - self.suspendtime)
            self.suspendtime = None

    # stop_queueing()
    #
    # Stop queueing additional jobs, causes Scheduler.run()
    # to return once all currently processing jobs are finished.
    #
    def stop_queueing(self):
        self.queue_jobs = False

    # elapsed_time()
    #
    # Fetches the current session elapsed time
    #
    # Returns:
    #    (datetime): The amount of time since the start of the session,
    #                discounting any time spent while jobs were suspended.
    #
    def elapsed_time(self):
        timenow = datetime.datetime.now()
        starttime = self.starttime
        if not starttime:
            starttime = timenow
        return timenow - starttime

    #######################################################
    #                   Main Loop Events                  #
    #######################################################
    def interrupt_event(self):
        # Leave this to the frontend to decide, if no
        # interrrupt callback was specified, then just terminate.
        if self.interrupt_callback:
            self.interrupt_callback()
        else:
            # Default without a frontend is just terminate
            self.terminate_jobs()

    def terminate_event(self):
        # Terminate gracefully if we receive SIGTERM
        self.terminate_jobs()

    def suspend_event(self):

        # Ignore the feedback signals from Job.suspend()
        if self.internal_stops:
            self.internal_stops -= 1
            return

        # No need to care if jobs were suspended or not, we _only_ handle this
        # while we know jobs are not suspended.
        self.suspend_jobs()
        os.kill(os.getpid(), signal.SIGSTOP)
        self.resume_jobs()

    #######################################################
    #                    Internal methods                 #
    #######################################################
    def connect_signals(self):
        self.loop.add_signal_handler(signal.SIGINT, self.interrupt_event)
        self.loop.add_signal_handler(signal.SIGTERM, self.terminate_event)
        self.loop.add_signal_handler(signal.SIGTSTP, self.suspend_event)

    def disconnect_signals(self):
        self.loop.remove_signal_handler(signal.SIGINT)
        self.loop.remove_signal_handler(signal.SIGTSTP)
        self.loop.remove_signal_handler(signal.SIGTERM)

    def failed_elements(self):
        failed = False
        for queue in self.queues:
            if queue.failed_elements:
                failed = True
                break
        return failed

    # get_job_token():
    #
    # Used by the Queue object to obtain a token for
    # processing a Job, if a Queue does not receive a token
    # then it must wait until a later time in order to
    # process pending jobs.
    #
    # Args:
    #    queue_type (QueueType): The type of token to obtain
    #
    # Returns:
    #    (bool): Whether a token was handed out or not
    #
    def get_job_token(self, queue_type):
        if self.job_tokens[queue_type] > 0:
            self.job_tokens[queue_type] -= 1
            return True
        return False

    # put_job_token():
    #
    # Return a job token to the scheduler. Tokens previously
    # received with get_job_token() must be returned to
    # the scheduler once the associated job is complete.
    #
    # Args:
    #    queue_type (QueueType): The type of token to obtain
    #
    def put_job_token(self, queue_type):
        self.job_tokens[queue_type] += 1

    def sched(self):

        if self.queue_jobs:

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

    # Regular timeout for driving status in the UI
    def tick(self):
        elapsed = self.elapsed_time()
        self.ticker_callback(elapsed)
        self.loop.call_later(1, self.tick)

    # Called by the Queue when starting a Job
    def job_starting(self, job):
        if self.job_start_callback:
            self.job_start_callback(job.element, job.action_name)

    # Called by the Queue when a Job completed
    def job_completed(self, job, success):
        if self.job_complete_callback:
            self.job_complete_callback(job.element, job.action_name, success)
