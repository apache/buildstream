#
#  Copyright (C) 2016 Codethink Limited
#  Copyright (C) 2019 Bloomberg Finance LP
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
import sys

# Local imports
from .resources import Resources
from .jobs import JobStatus
from ..types import FastEnum
from .._profile import Topics, PROFILER
from .._message import Message, MessageType
from ..plugin import Plugin


_MAX_TIMEOUT_TO_KILL_CHILDREN = 20  # in seconds


# A decent return code for Scheduler.run()
class SchedStatus(FastEnum):
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
class Scheduler:
    def __init__(self, context, start_time, state, interrupt_callback, ticker_callback):

        #
        # Public members
        #
        self.queues = None  # Exposed for the frontend to print summaries
        self.context = context  # The Context object shared with Queues
        self.terminated = False  # Whether the scheduler was asked to terminate or has terminated
        self.suspended = False  # Whether the scheduler is currently suspended

        # These are shared with the Job, but should probably be removed or made private in some way.
        self.loop = None  # Shared for Job access to observe the message queue
        self.internal_stops = 0  # Amount of SIGSTP signals we've introduced, this is shared with job.py

        #
        # Private members
        #
        self._active_jobs = []  # Jobs currently being run in the scheduler
        self._suspendtime = None  # Session time compensation for suspended state
        self._queue_jobs = True  # Whether we should continue to queue jobs
        self._state = state
        self._casd_process = None  # handle to the casd process for monitoring purpose

        self._sched_handle = None  # Whether a scheduling job is already scheduled or not

        self._ticker_callback = ticker_callback
        self._interrupt_callback = interrupt_callback

        self.resources = Resources(context.sched_builders, context.sched_fetchers, context.sched_pushers)
        self._state.register_task_retry_callback(self._failure_retry)

    # run()
    #
    # Args:
    #    queues (list): A list of Queue objects
    #    casd_process_manager (cascache.CASDProcessManager): The subprocess which runs casd, in order to be notified
    #                                                        of failures.
    #
    # Returns:
    #    (SchedStatus): How the scheduling terminated
    #
    # Elements in the 'plan' will be processed by each
    # queue in order. Processing will complete when all
    # elements have been processed by each queue or when
    # an error arises
    #
    def run(self, queues, casd_process_manager):

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
        self.loop.call_later(1, self._tick)

        # Add exception handler
        self.loop.set_exception_handler(self._handle_exception)

        # Handle unix signals while running
        self._connect_signals()

        # Watch casd while running to ensure it doesn't die
        self._casd_process = casd_process_manager.process
        _watcher = asyncio.get_child_watcher()

        def abort_casd(pid, returncode):
            asyncio.get_event_loop().call_soon(self._abort_on_casd_failure, pid, returncode)

        _watcher.add_child_handler(self._casd_process.pid, abort_casd)

        # Start the profiler
        with PROFILER.profile(Topics.SCHEDULER, "_".join(queue.action_name for queue in self.queues)):
            # Run the queues
            self._sched()
            self.loop.run_forever()
            self.loop.close()

        # Stop watching casd
        _watcher.remove_child_handler(self._casd_process.pid)
        self._casd_process = None

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

    # terminate()
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
    def terminate(self):

        # Set this right away, the frontend will check this
        # attribute to decide whether or not to print status info
        # etc and the following code block will trigger some callbacks.
        self.terminated = True

        # Notify the frontend that we're terminated as it might be
        # from an interactive prompt callback or SIGTERM
        self.loop.call_soon(self._terminate_jobs_real)

        # Block this until we're finished terminating jobs,
        # this will remain blocked forever.
        signal.pthread_sigmask(signal.SIG_BLOCK, [signal.SIGINT])

    # suspend()
    #
    # Suspend the scheduler
    #
    def suspend(self):
        self._disconnect_signals()
        self._suspend_jobs()

    # resume()
    #
    # Restart the scheduler
    #
    def resume(self):
        self._resume_jobs()
        self._connect_signals()

    # stop()
    #
    # Stop queueing additional jobs, causes Scheduler.run()
    # to return once all currently processing jobs are finished.
    #
    def stop(self):
        self._queue_jobs = False

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

        if status == JobStatus.FAIL:
            # If it's an elementjob, we want to compare against the failure messages
            # and send the unique_id and display key tuple of the Element. This can then
            # be used to load the element instance relative to the process it is running in.
            element = job.get_element()
            if element:
                element_info = element._unique_id, element._get_display_key()
            else:
                element_info = None

            self._state.fail_task(job.action_name, job.name, element_info)

        self._state.remove_task(job.action_name, job.name)

        self._sched()

    #######################################################
    #                  Local Private Methods              #
    #######################################################

    # _abort_on_casd_failure()
    #
    # Abort if casd failed while running.
    #
    # This will terminate immediately all jobs, since buildbox-casd is dead,
    # we can't do anything with them anymore.
    #
    # Args:
    #   pid (int): the process id under which buildbox-casd was running
    #   returncode (int): the return code with which buildbox-casd exited
    #
    def _abort_on_casd_failure(self, pid, returncode):
        message = Message(MessageType.BUG, "buildbox-casd died while the pipeline was active.")
        self.context.messenger.message(message)

        self._casd_process.returncode = returncode
        self.terminate()

    # _start_job()
    #
    # Spanws a job
    #
    # Args:
    #    job (Job): The job to start
    #
    def _start_job(self, job):

        # From the scheduler perspective, the following
        # is considered atomic; started jobs are always in the
        # active_jobs list, and jobs in the active_jobs list
        # are always started.
        #
        self._active_jobs.append(job)
        job.start()

        self._state.add_task(job.action_name, job.name, self._state.elapsed_time())

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
            ready.extend(chain.from_iterable(q.harvest_jobs() for q in reversed(self.queues)))

            # harvest_jobs() may have decided to skip some jobs, making
            # them eligible for promotion to the next queue as a side effect.
            #
            # If that happens, do another round.
            process_queues = any(q.dequeue_ready() for q in self.queues)

        # Make sure fork is allowed before starting jobs
        if not self.context.prepare_fork():
            message = Message(MessageType.BUG, "Fork is not allowed", detail="Background threads are active")
            self.context.messenger.message(message)
            self.terminate()
            return

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
        def real_schedule():

            # Reset the scheduling handle before queuing any jobs.
            #
            # We do this right away because starting jobs can result
            # in their being terminated and completed during the body
            # of this function, and we want to be sure that we get
            # called again in this case.
            #
            # This can happen if jobs are explicitly killed as a result,
            # which might happen as a side effect of a crash in an
            # abstracted frontend implementation handling notifications
            # about jobs starting.
            #
            self._sched_handle = None

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

        if self._sched_handle is None:
            self._sched_handle = self.loop.call_soon(real_schedule)

    # _suspend_jobs()
    #
    # Suspend all ongoing jobs.
    #
    def _suspend_jobs(self):
        if not self.suspended:
            self._suspendtime = datetime.datetime.now()
            self.suspended = True
            # Notify that we're suspended
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
            # Notify that we're unsuspended
            self._state.offset_start_time(datetime.datetime.now() - self._suspendtime)
            self._suspendtime = None

    # _interrupt_event():
    #
    # A loop registered event callback for keyboard interrupts
    #
    def _interrupt_event(self):

        # The event loop receives a copy of all signals that are sent while it is running
        # This means that even though we catch the SIGINT in the question to the user,
        # the loop will receive it too, and thus we need to skip it here.
        if self.terminated:
            return

        self._interrupt_callback()

    # _terminate_event():
    #
    # A loop registered event callback for SIGTERM
    #
    def _terminate_event(self):
        self.terminate()

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

        # Schedule all jobs to be killed if they have not exited after timeout
        self.loop.call_later(_MAX_TIMEOUT_TO_KILL_CHILDREN, kill_jobs)

        for job in self._active_jobs:
            job.terminate()

    # Regular timeout for driving status in the UI
    def _tick(self):
        self._ticker_callback()
        self.loop.call_later(1, self._tick)

    def _failure_retry(self, action_name, unique_id):
        queue = None
        for q in self.queues:
            if q.action_name == action_name:
                queue = q
                break
        # Assert queue found, we should only be retrying a queued job
        assert queue
        element = Plugin._lookup(unique_id)
        queue._task_group.failed_tasks.remove(element._get_full_name())
        queue.enqueue([element])

    def _handle_exception(self, loop, context: dict) -> None:
        e = context.get("exception")
        exc = bool(e)
        if e is None:
            # https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.call_exception_handler
            # If no optional Exception generate a generic exception with message value.
            # exc will be False, instructing the global handler to skip formatting the
            # assumed exception & related traceback.
            e = Exception(str(context.get("message")) + " asyncio exception handler called, but no Exception() given")

        # Call the sys global exception handler directly, as to avoid the default
        # async handler raising an unhandled exception here. App will treat this
        # as a 'BUG', format it appropriately & exit. mypy needs to ignore parameter
        # types here as we're overriding sys globally in App._global_exception_handler()
        sys.excepthook(type(e), e, e.__traceback__, exc)  # type: ignore
