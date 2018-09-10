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
from .resources import Resources, ResourceType
from .jobs import CacheSizeJob, CleanupJob
from .._platform import Platform


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
        self.active_jobs = []       # Jobs currently being run in the scheduler
        self.waiting_jobs = []      # Jobs waiting for resources
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

        self._resources = Resources(context.sched_builders,
                                    context.sched_fetchers,
                                    context.sched_pushers)

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
        self._schedule_queue_jobs()
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

    # schedule_jobs()
    #
    # Args:
    #     jobs ([Job]): A list of jobs to schedule
    #
    # Schedule 'Job's for the scheduler to run. Jobs scheduled will be
    # run as soon any other queueing jobs finish, provided sufficient
    # resources are available for them to run
    #
    def schedule_jobs(self, jobs):
        for job in jobs:
            self.waiting_jobs.append(job)

    # job_completed():
    #
    # Called when a Job completes
    #
    # Args:
    #    queue (Queue): The Queue holding a complete job
    #    job (Job): The completed Job
    #    success (bool): Whether the Job completed with a success status
    #
    def job_completed(self, job, success):
        self._resources.clear_job_resources(job)
        self.active_jobs.remove(job)
        self._job_complete_callback(job, success)
        self._schedule_queue_jobs()
        self._sched()

    # check_cache_size():
    #
    # Queues a cache size calculation job, after the cache
    # size is calculated, a cleanup job will be run automatically
    # if needed.
    #
    # FIXME: This should ensure that only one cache size job
    #        is ever pending at a given time. If a cache size
    #        job is already running, it is correct to queue
    #        a new one, it is incorrect to have more than one
    #        of these jobs pending at a given time, though.
    #
    def check_cache_size(self):
        job = CacheSizeJob(self, 'cache_size', 'cache_size/cache_size',
                           resources=[ResourceType.CACHE,
                                      ResourceType.PROCESS],
                           complete_cb=self._run_cleanup)
        self.schedule_jobs([job])

    #######################################################
    #                  Local Private Methods              #
    #######################################################

    # _sched()
    #
    # The main driving function of the scheduler, it will be called
    # automatically when Scheduler.run() is called initially,
    #
    def _sched(self):
        for job in self.waiting_jobs:
            self._resources.reserve_exclusive_resources(job)

        for job in self.waiting_jobs:
            if not self._resources.reserve_job_resources(job):
                continue

            job.spawn()
            self.waiting_jobs.remove(job)
            self.active_jobs.append(job)

            if self._job_start_callback:
                self._job_start_callback(job)

        # If nothings ticking, time to bail out
        if not self.active_jobs and not self.waiting_jobs:
            self.loop.stop()

    # _schedule_queue_jobs()
    #
    # Ask the queues what jobs they want to schedule and schedule
    # them. This is done here so we can ask for new jobs when jobs
    # from previous queues become available.
    #
    # This will process the Queues, pull elements through the Queues
    # and process anything that is ready.
    #
    def _schedule_queue_jobs(self):
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
                queue.pop_ready_jobs() for queue in reversed(self.queues)
            ))

            # pop_ready_jobs() may have skipped jobs, adding them to
            # the done_queue.  Pull these skipped elements forward to
            # the next queue and process them.
            process_queues = any(q.dequeue_ready() for q in self.queues)

        self.schedule_jobs(ready)
        self._sched()

    # _run_cleanup()
    #
    # Schedules the cache cleanup job if the passed size
    # exceeds the cache quota.
    #
    # Args:
    #    cache_size (int): The calculated cache size (ignored)
    #
    # NOTE: This runs in response to completion of the cache size
    #       calculation job lauched by Scheduler.check_cache_size(),
    #       which will report the calculated cache size.
    #
    def _run_cleanup(self, cache_size):
        platform = Platform.get_platform()
        artifacts = platform.artifactcache

        if not artifacts.get_quota_exceeded():
            return

        job = CleanupJob(self, 'cleanup', 'cleanup/cleanup',
                         resources=[ResourceType.CACHE,
                                    ResourceType.PROCESS],
                         exclusive_resources=[ResourceType.CACHE],
                         complete_cb=None)
        self.schedule_jobs([job])

    # _suspend_jobs()
    #
    # Suspend all ongoing jobs.
    #
    def _suspend_jobs(self):
        if not self.suspended:
            self._suspendtime = datetime.datetime.now()
            self.suspended = True
            for job in self.active_jobs:
                job.suspend()

    # _resume_jobs()
    #
    # Resume suspended jobs.
    #
    def _resume_jobs(self):
        if self.suspended:
            for job in self.active_jobs:
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

        # First tell all jobs to terminate
        for job in self.active_jobs:
            job.terminate()

        # Now wait for them to really terminate
        for job in self.active_jobs:
            elapsed = datetime.datetime.now() - wait_start
            timeout = max(wait_limit - elapsed.total_seconds(), 0.0)
            if not job.terminate_wait(timeout):
                job.kill()

        # Clear out the waiting jobs
        self.waiting_jobs = []

    # Regular timeout for driving status in the UI
    def _tick(self):
        elapsed = self.elapsed_time()
        self._ticker_callback(elapsed)
        self.loop.call_later(1, self._tick)
