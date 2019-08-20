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
from .resources import Resources
from .jobs import JobStatus
from .._profile import Topics, PROFILER


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
# elements have been traversed or when an error occurs.
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
#    state: The state that can be made available to the frontend
#    interrupt_callback: A callback to handle ^C
#    ticker_callback: A callback call once per second
#
class Scheduler():

    def __init__(self, context,
                 start_time, state,
                 interrupt_callback=None,
                 ticker_callback=None):

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
        self._state = state

        # Callbacks to report back to the Scheduler owner
        self._interrupt_callback = interrupt_callback
        self._ticker_callback = ticker_callback

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

        assert self.context.fork_allowed

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

        # Start the profiler
        with PROFILER.profile(Topics.SCHEDULER, "_".join(queue.action_name for queue in self.queues)):
            # Run the queues
            self._sched()
            self.loop.run_forever()
            self.loop.close()

        # Stop handling unix signals
        self._disconnect_signals()

        failed = any(queue.any_failed_elements() for queue in self.queues)
        self.loop = None

        if failed:
            status = SchedStatus.ERROR
        elif self.terminated:
            status = SchedStatus.TERMINATED
        else:
            status = SchedStatus.SUCCESS

        return status

    # clear_queues()
    #
    # Forcibly destroys all the scheduler's queues
    # This is needed because Queues register TaskGroups with State,
    # which must be unique. As there is not yet any reason to have multiple
    # Queues of the same type, old ones should be deleted.
    #
    def clear_queues(self):
        if self.queues:
            for queue in self.queues:
                queue.destroy()

            self.queues.clear()

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
    #    (timedelta): The amount of time since the start of the session,
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

        self._state.remove_task(job.action_name, job.name)
        if status == JobStatus.FAIL:
            # If it's an elementjob, we want to compare against the failure messages
            # and send the unique_id and display key tuple of the Element. This can then
            # be used to load the element instance relative to the process it is running in.
            element = job.get_element()
            if element:
                element_info = element._unique_id, element._get_display_key()
            else:
                element_info = None
            self._state.fail_task(job.action_name, job.name, element=element_info)

        # Now check for more jobs
        self._sched()

    #######################################################
    #                  Local Private Methods              #
    #######################################################

    # _start_job()
    #
    # Spanws a job
    #
    # Args:
    #    job (Job): The job to start
    #
    def _start_job(self, job):
        self._active_jobs.append(job)
        self._state.add_task(job.action_name, job.name, self.elapsed_time())
        job.start()

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

        # Start the jobs
        #
        for job in ready:
            self._start_job(job)

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
        # 20 seconds is a long time, it can take a while and sometimes
        # we still fail, need to look deeper into this again.
        wait_start = datetime.datetime.now()
        wait_limit = 20.0

        # First tell all jobs to terminate
        for job in self._active_jobs:
            job.terminate()

        # Now wait for them to really terminate
        for job in self._active_jobs:
            elapsed = datetime.datetime.now() - wait_start
            timeout = max(wait_limit - elapsed.total_seconds(), 0.0)
            if not job.terminate_wait(timeout):
                job.kill()

    # Regular timeout for driving status in the UI
    def _tick(self):
        self._ticker_callback()
        self.loop.call_later(1, self._tick)

    def __getstate__(self):
        # The only use-cases for pickling in BuildStream at the time of writing
        # are enabling the 'spawn' method of starting child processes, and
        # saving jobs to disk for replays.
        #
        # In both of these use-cases, a common mistake is that something being
        # pickled indirectly holds a reference to the Scheduler, which in turn
        # holds lots of things that are not pickleable.
        #
        # Make this situation easier to debug by failing early, in the
        # Scheduler itself. Pickling this is almost certainly a mistake, unless
        # a new use-case arises.
        #
        raise TypeError("Scheduler objects should not be pickled.")
