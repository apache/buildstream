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
from itertools import chain
import signal
import datetime
from contextlib import contextmanager

# Local imports
from .jobs import JobType
from .queues import QueueType


# A decent return code for Scheduler.run()
class SchedStatus():
    SUCCESS = 0
    ERROR = -1
    TERMINATED = 1


# A set of rules that dictates in which order jobs should run.
#
# The first tuple defines jobs that are not allowed to be executed
# before the current job completes (even if the job is still waiting
# to be executed).
#
# The second tuple defines jobs that the current job is not allowed to
# be run in parallel with.
#
# Note that this is very different from the element job
# dependencies. Both a build and fetch job can be ready at the same
# time, this has nothing to do with the requirement to fetch sources
# before building. These rules are purely in place to maintain cache
# consistency.
#
JOB_RULES = {
    JobType.CLEAN: {
        # Build and pull jobs are not allowed to run when we are about
        # to start a cleanup job, because they will add more data to
        # the artifact cache.
        'priority': (JobType.BUILD, JobType.PULL),
        # Cleanup jobs are not allowed to run in parallel with any
        # jobs that might need to access the artifact cache, because
        # we cannot guarantee atomicity otherwise.
        'exclusive': (JobType.BUILD, JobType.PULL, JobType.PUSH)
    },
    JobType.BUILD: {
        'priority': (),
        'exclusive': ()
    },
    JobType.FETCH: {
        'priority': (),
        'exclusive': ()
    },
    JobType.PULL: {
        'priority': (),
        'exclusive': ()
    },
    JobType.PUSH: {
        'priority': (),
        'exclusive': ()
    },
    JobType.SIZE: {
        'priority': (),
        'exclusive': ()
    },
    JobType.TRACK: {
        'priority': (),
        'exclusive': ()
    }
}


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
#    start_time: The time at which the session started
#    interrupt_callback: A callback to handle ^C
#    ticker_callback: A callback call once per second
#    job_start_callback: A callback call when each job starts
#    job_complete_callback: A callback call when each job completes
#
class Scheduler():

    def __init__(self, context,
                 start_time,
                 interrupt_callback=None,
                 ticker_callback=None,
                 job_start_callback=None,
                 job_complete_callback=None):

        #
        # Public members
        #
        self.waiting_jobs = []      # Jobs waiting for execution
        self.active_jobs = []       # Jobs currently being run in the scheduler
        self.queues = None          # Exposed for the frontend to print summaries
        self.context = context      # The Context object shared with Queues
        self.terminated = False     # Whether the scheduler was asked to terminate or has terminated
        self.suspended = False      # Whether the scheduler is currently suspended

        # These are shared with the Job, but should probably be removed or made private in some way.
        self.loop = None            # Shared for Job access to observe the message queue
        self.internal_stops = 0     # Amount of SIGSTP signals we've introduced, this is shared with job.py

        #
        # Private members
        #
        self._interrupt_callback = interrupt_callback
        self._ticker_callback = ticker_callback
        self._job_start_callback = job_start_callback
        self._job_complete_callback = job_complete_callback

        self._starttime = start_time
        self._suspendtime = None
        self._queue_jobs = True      # Whether we should continue to queue jobs

        # Initialize task tokens with the number allowed by
        # the user configuration
        self._job_tokens = {
            QueueType.FETCH: context.sched_fetchers,
            QueueType.BUILD: context.sched_builders,
            QueueType.PUSH: context.sched_pushers
        }

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

        # Hold on to the queues to process
        self.queues = queues

        # Ensure that we have a fresh new event loop, in case we want
        # to run another test in this thread.
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # Add timeouts
        if self._ticker_callback:
            self.loop.call_later(1, self._tick)

        # Handle unix signals while running
        self._connect_signals()

        # Run the queues
        self.schedule_queue_jobs()
        self.loop.run_forever()
        self.loop.close()

        # Stop handling unix signals
        self._disconnect_signals()

        failed = any(any(queue.failed_elements) for queue in self.queues)
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
    # For this to be effective, one needs to return to
    # the scheduler loop first and allow the scheduler
    # to complete gracefully.
    #
    # NOTE: This will block SIGINT so that graceful process
    #       termination is not interrupted, and SIGINT will
    #       remain blocked after Scheduler.run() returns.
    #
    def terminate_jobs(self):

        # Set this right away, the frontend will check this
        # attribute to decide whether or not to print status info
        # etc and the following code block will trigger some callbacks.
        self.terminated = True
        self.loop.call_soon(self._terminate_jobs_real)

        # Block this until we're finished terminating jobs,
        # this will remain blocked forever.
        signal.pthread_sigmask(signal.SIG_BLOCK, [signal.SIGINT])

    # jobs_suspended()
    #
    # A context manager for running with jobs suspended
    #
    @contextmanager
    def jobs_suspended(self):
        self._disconnect_signals()
        self._suspend_jobs()

        yield

        self._resume_jobs()
        self._connect_signals()

    # stop_queueing()
    #
    # Stop queueing additional jobs, causes Scheduler.run()
    # to return once all currently processing jobs are finished.
    #
    def stop_queueing(self):
        self._queue_jobs = False

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
        starttime = self._starttime
        if not starttime:
            starttime = timenow
        return timenow - starttime

    # sched()
    #
    # The main driving function of the scheduler, it will be called
    # automatically when Scheduler.run() is called initially, and needs
    # to be called whenever a job can potentially be scheduled, usually
    # when a Queue completes handling of a job.
    #
    # This will process the Queues and pull elements through the Queues
    # and process anything that is ready.
    #
    def sched(self):
        for job in self.waiting_jobs:
            # If our job is not allowed to run with any job currently
            # running, we don't start it.
            if any(running_job.job_type in JOB_RULES[job.job_type]['exclusive']
                   for running_job in self.active_jobs):
                continue

            # If any job currently waiting has priority over this one,
            # we don't start it.
            if any(job.job_type in JOB_RULES[waiting_job.job_type]['priority']
                   for waiting_job in self.waiting_jobs):
                continue

            job.spawn()
            self.waiting_jobs.remove(job)
            self.active_jobs.append(job)

            if self._job_start_callback:
                self._job_start_callback(job)

        # If nothings ticking, time to bail out
        if not self.active_jobs and not self.waiting_jobs:
            self.loop.stop()

    def schedule_jobs(self, jobs):
        self.waiting_jobs.extend(jobs)

    def schedule_queue_jobs(self):
        ready = []
        process_queues = True

        while self._queue_jobs and process_queues:
            # Pull elements forward through queues
            elements = []
            for queue in self.queues:
                # Enqueue elements complete from the last queue
                queue.enqueue(elements)

                # Dequeue processed elements for the next queue
                elements = list(queue.dequeue())

            # Kickoff whatever processes can be processed at this time
            #
            # We start by queuing from the last queue first, because
            # we want to give priority to queues later in the
            # scheduling process in the case that multiple queues
            # share the same token type.
            #
            # This avoids starvation situations where we dont move on
            # to fetch tasks for elements which failed to pull, and
            # thus need all the pulls to complete before ever starting
            # a build
            ready.extend(chain.from_iterable(
                queue.process_ready() for queue in reversed(self.queues)
            ))

            # process_ready() may have skipped jobs, adding them to
            # the done_queue.  Pull these skipped elements forward to
            # the next queue and process them.
            process_queues = any(q.dequeue_ready() for q in self.queues)

        self.schedule_jobs(ready)
        self.sched()

    # job_completed():
    #
    # Called when a Job completes
    #
    # Args:
    #    queue (Queue): The Queue holding a complete job
    #    job (Job): The completed Job
    #    success (bool): Whether the Job completed with a success status
    #
    def job_completed(self, job):
        self.active_jobs.remove(job)
        self.schedule_queue_jobs()

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
        if self._job_tokens[queue_type] > 0:
            self._job_tokens[queue_type] -= 1
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
        self._job_tokens[queue_type] += 1

    #######################################################
    #                  Local Private Methods              #
    #######################################################

    # _suspend_jobs()
    #
    # Suspend all ongoing jobs.
    #
    def _suspend_jobs(self):
        if not self.suspended:
            self._suspendtime = datetime.datetime.now()
            self.suspended = True
            for queue in self.queues:
                for job in queue.active_jobs:
                    job.suspend()

    # _resume_jobs()
    #
    # Resume suspended jobs.
    #
    def _resume_jobs(self):
        if self.suspended:
            for queue in self.queues:
                for job in queue.active_jobs:
                    job.resume()
            self.suspended = False
            self._starttime += (datetime.datetime.now() - self._suspendtime)
            self._suspendtime = None

    # _interrupt_event():
    #
    # A loop registered event callback for keyboard interrupts
    #
    def _interrupt_event(self):
        # Leave this to the frontend to decide, if no
        # interrrupt callback was specified, then just terminate.
        if self._interrupt_callback:
            self._interrupt_callback()
        else:
            # Default without a frontend is just terminate
            self.terminate_jobs()

    # _terminate_event():
    #
    # A loop registered event callback for SIGTERM
    #
    def _terminate_event(self):
        self.terminate_jobs()

    # _suspend_event():
    #
    # A loop registered event callback for SIGTSTP
    #
    def _suspend_event(self):

        # Ignore the feedback signals from Job.suspend()
        if self.internal_stops:
            self.internal_stops -= 1
            return

        # No need to care if jobs were suspended or not, we _only_ handle this
        # while we know jobs are not suspended.
        self._suspend_jobs()
        os.kill(os.getpid(), signal.SIGSTOP)
        self._resume_jobs()

    # _connect_signals():
    #
    # Connects our signal handler event callbacks to the mainloop
    #
    def _connect_signals(self):
        self.loop.add_signal_handler(signal.SIGINT, self._interrupt_event)
        self.loop.add_signal_handler(signal.SIGTERM, self._terminate_event)
        self.loop.add_signal_handler(signal.SIGTSTP, self._suspend_event)

    def _disconnect_signals(self):
        self.loop.remove_signal_handler(signal.SIGINT)
        self.loop.remove_signal_handler(signal.SIGTSTP)
        self.loop.remove_signal_handler(signal.SIGTERM)

    def _terminate_jobs_real(self):
        # 20 seconds is a long time, it can take a while and sometimes
        # we still fail, need to look deeper into this again.
        wait_start = datetime.datetime.now()
        wait_limit = 20.0

        active_jobs = self.active_jobs
        for queue in self.queues:
            active_jobs.extend(queue.active_jobs)

        # First tell all jobs to terminate
        for job in active_jobs:
            job.terminate()

        # Now wait for them to really terminate
        for job in active_jobs:
            elapsed = datetime.datetime.now() - wait_start
            timeout = max(wait_limit - elapsed.total_seconds(), 0.0)
            if not job.terminate_wait(timeout):
                job.kill()

        self.loop.stop()

    # Regular timeout for driving status in the UI
    def _tick(self):
        elapsed = self.elapsed_time()
        self._ticker_callback(elapsed)
        self.loop.call_later(1, self._tick)
