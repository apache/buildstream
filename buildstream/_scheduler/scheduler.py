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
from .jobs import JobStatus, CacheSizeJob, CleanupJob


# A decent return code for Scheduler.run()
class SchedStatus():
    SUCCESS = 0
    ERROR = -1
    TERMINATED = 1


# Some action names for the internal jobs we launch
#
_ACTION_NAME_CLEANUP = 'cleanup'
_ACTION_NAME_CACHE_SIZE = 'cache_size'


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
        self._active_jobs = []                # Jobs currently being run in the scheduler
        self._starttime = start_time          # Initial application start time
        self._suspendtime = None              # Session time compensation for suspended state
        self._queue_jobs = True               # Whether we should continue to queue jobs

        # State of cache management related jobs
        self._cache_size_scheduled = False    # Whether we have a cache size job scheduled
        self._cache_size_running = None       # A running CacheSizeJob, or None
        self._cleanup_scheduled = False       # Whether we have a cleanup job scheduled
        self._cleanup_running = None          # A running CleanupJob, or None

        # Callbacks to report back to the Scheduler owner
        self._interrupt_callback = interrupt_callback
        self._ticker_callback = ticker_callback
        self._job_start_callback = job_start_callback
        self._job_complete_callback = job_complete_callback

        # Whether our exclusive jobs, like 'cleanup' are currently already
        # waiting or active.
        #
        # This is just a bit quicker than scanning the wait queue and active
        # queue and comparing job action names.
        #
        self._exclusive_waiting = set()
        self._exclusive_active = set()

        self.resources = Resources(context.sched_builders,
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

        # NOTE: Enforce use of `SafeChildWatcher` as we generally don't want
        # background threads.
        # In Python 3.8+, `ThreadedChildWatcher` is the default watcher, and
        # not `SafeChildWatcher`.
        asyncio.set_child_watcher(asyncio.SafeChildWatcher())

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
        self._sched()
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

    # job_completed():
    #
    # Called when a Job completes
    #
    # Args:
    #    queue (Queue): The Queue holding a complete job
    #    job (Job): The completed Job
    #    status (JobStatus): The status of the completed job
    #
    def job_completed(self, job, status):

        # Remove from the active jobs list
        self._active_jobs.remove(job)

        # Scheduler owner facing callback
        self._job_complete_callback(job, status)

        # Now check for more jobs
        self._sched()

    # check_cache_size():
    #
    # Queues a cache size calculation job, after the cache
    # size is calculated, a cleanup job will be run automatically
    # if needed.
    #
    def check_cache_size(self):

        # Here we assume we are called in response to a job
        # completion callback, or before entering the scheduler.
        #
        # As such there is no need to call `_sched()` from here,
        # and we prefer to run it once at the last moment.
        #
        self._cache_size_scheduled = True

    #######################################################
    #                  Local Private Methods              #
    #######################################################

    # _spawn_job()
    #
    # Spanws a job
    #
    # Args:
    #    job (Job): The job to spawn
    #
    def _spawn_job(self, job):
        job.spawn()
        self._active_jobs.append(job)
        if self._job_start_callback:
            self._job_start_callback(job)

    # Callback for the cache size job
    def _cache_size_job_complete(self, status, cache_size):
        context = self.context
        artifacts = context.artifactcache

        # Deallocate cache size job resources
        self._cache_size_running = None
        self.resources.release([ResourceType.CACHE, ResourceType.PROCESS])

        # Schedule a cleanup job if we've hit the threshold
        if status != JobStatus.OK:
            return

        if artifacts.has_quota_exceeded():
            self._cleanup_scheduled = True

    # Callback for the cleanup job
    def _cleanup_job_complete(self, status, cache_size):

        # Deallocate cleanup job resources
        self._cleanup_running = None
        self.resources.release([ResourceType.CACHE, ResourceType.PROCESS])

        # Unregister the exclusive interest when we're done with it
        if not self._cleanup_scheduled:
            self.resources.unregister_exclusive_interest(
                [ResourceType.CACHE], 'cache-cleanup'
            )

    # _sched_cleanup_job()
    #
    # Runs a cleanup job if one is scheduled to run now and
    # sufficient recources are available.
    #
    def _sched_cleanup_job(self):

        if self._cleanup_scheduled and self._cleanup_running is None:

            # Ensure we have an exclusive interest in the resources
            self.resources.register_exclusive_interest(
                [ResourceType.CACHE], 'cache-cleanup'
            )

            if self.resources.reserve([ResourceType.CACHE, ResourceType.PROCESS],
                                      [ResourceType.CACHE]):

                # Update state and launch
                self._cleanup_scheduled = False
                self._cleanup_running = \
                    CleanupJob(self, _ACTION_NAME_CLEANUP, 'cleanup/cleanup',
                               complete_cb=self._cleanup_job_complete)
                self._spawn_job(self._cleanup_running)

    # _sched_cache_size_job()
    #
    # Runs a cache size job if one is scheduled to run now and
    # sufficient recources are available.
    #
    def _sched_cache_size_job(self):

        if self._cache_size_scheduled and not self._cache_size_running:

            if self.resources.reserve([ResourceType.CACHE, ResourceType.PROCESS]):
                self._cache_size_scheduled = False
                self._cache_size_running = \
                    CacheSizeJob(self, _ACTION_NAME_CACHE_SIZE,
                                 'cache_size/cache_size',
                                 complete_cb=self._cache_size_job_complete)
                self._spawn_job(self._cache_size_running)

    # _sched_queue_jobs()
    #
    # Ask the queues what jobs they want to schedule and schedule
    # them. This is done here so we can ask for new jobs when jobs
    # from previous queues become available.
    #
    # This will process the Queues, pull elements through the Queues
    # and process anything that is ready.
    #
    def _sched_queue_jobs(self):
        ready = []
        process_queues = True

        while self._queue_jobs and process_queues:

            # Pull elements forward through queues
            elements = []
            for queue in self.queues:
                queue.enqueue(elements)
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
                q.harvest_jobs() for q in reversed(self.queues)
            ))

            # harvest_jobs() may have decided to skip some jobs, making
            # them eligible for promotion to the next queue as a side effect.
            #
            # If that happens, do another round.
            process_queues = any(q.dequeue_ready() for q in self.queues)

        # Spawn the jobs
        #
        for job in ready:
            self._spawn_job(job)

    # _sched()
    #
    # Run any jobs which are ready to run, or quit the main loop
    # when nothing is running or is ready to run.
    #
    # This is the main driving function of the scheduler, it is called
    # initially when we enter Scheduler.run(), and at the end of whenever
    # any job completes, after any bussiness logic has occurred and before
    # going back to sleep.
    #
    def _sched(self):

        if not self.terminated:

            #
            # Try the cache management jobs
            #
            self._sched_cleanup_job()
            self._sched_cache_size_job()

            #
            # Run as many jobs as the queues can handle for the
            # available resources
            #
            self._sched_queue_jobs()

        #
        # If nothing is ticking then bail out
        #
        if not self._active_jobs:
            self.loop.stop()

    # _suspend_jobs()
    #
    # Suspend all ongoing jobs.
    #
    def _suspend_jobs(self):
        if not self.suspended:
            self._suspendtime = datetime.datetime.now()
            self.suspended = True
            for job in self._active_jobs:
                job.suspend()

    # _resume_jobs()
    #
    # Resume suspended jobs.
    #
    def _resume_jobs(self):
        if self.suspended:
            for job in self._active_jobs:
                job.resume()
            self.suspended = False
            self._starttime += (datetime.datetime.now() - self._suspendtime)
            self._suspendtime = None

    # _interrupt_event():
    #
    # A loop registered event callback for keyboard interrupts
    #
    def _interrupt_event(self):

        # FIXME: This should not be needed, but for some reason we receive an
        #        additional SIGINT event when the user hits ^C a second time
        #        to inform us that they really intend to terminate; even though
        #        we have disconnected our handlers at this time.
        #
        if self.terminated:
            return

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
        def kill_jobs():
            for job_ in self._active_jobs:
                job_.kill()

        # Schedule all jobs to be killed if they have not exited in 20 sec
        self.loop.call_later(20, kill_jobs)

        for job in self._active_jobs:
            job.terminate()

    # Regular timeout for driving status in the UI
    def _tick(self):
        elapsed = self.elapsed_time()
        self._ticker_callback(elapsed)
        self.loop.call_later(1, self._tick)
