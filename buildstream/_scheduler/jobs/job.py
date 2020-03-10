#
#  Copyright (C) 2018 Codethink Limited
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
#        Tristan Maat <tristan.maat@codethink.co.uk>

# System imports
import os
import sys
import signal
import datetime
import traceback
import asyncio
import multiprocessing

# BuildStream toplevel imports
from ..._exceptions import ImplError, BstError, set_last_task_error, SkipJob
from ..._message import Message, MessageType, unconditional_messages
from ... import _signals, utils
from .. import _multiprocessing

# Return code values shutdown of job handling child processes
#
RC_OK = 0
RC_FAIL = 1
RC_PERM_FAIL = 2
RC_SKIPPED = 3


# JobStatus:
#
# The job completion status, passed back through the
# complete callbacks.
#
class JobStatus():
    # Job succeeded
    OK = 0

    # A temporary BstError was raised
    FAIL = 1

    # A SkipJob was raised
    SKIPPED = 3


# Used to distinguish between status messages and return values
class _Envelope():
    def __init__(self, message_type, message):
        self.message_type = message_type
        self.message = message


# Job()
#
# The Job object represents a parallel task, when calling Job.spawn(),
# the given `Job.child_process()` will be called in parallel to the
# calling process, and `Job.parent_complete()` will be called with the
# action result in the calling process when the job completes.
#
# Args:
#    scheduler (Scheduler): The scheduler
#    action_name (str): The queue action name
#    logfile (str): A template string that points to the logfile
#                   that should be used - should contain {pid}.
#    max_retries (int): The maximum number of retries
#
class Job():

    def __init__(self, scheduler, action_name, logfile, *, max_retries=0):

        #
        # Public members
        #
        self.action_name = action_name   # The action name for the Queue
        self.child_data = None           # Data to be sent to the main process

        #
        # Private members
        #
        self._scheduler = scheduler            # The scheduler
        self._queue = multiprocessing.Queue()  # A message passing queue
        self._process = None                   # The Process object
        self._watcher = None                   # Child process watcher
        self._listening = False                # Whether the parent is currently listening
        self._suspended = False                # Whether this job is currently suspended
        self._max_retries = max_retries        # Maximum number of automatic retries
        self._result = None                    # Return value of child action in the parent
        self._tries = 0                        # Try count, for retryable jobs
        self._terminated = False               # Whether this job has been explicitly terminated

        # If False, a retry will not be attempted regardless of whether _tries is less than _max_retries.
        #
        self._retry_flag = True
        self._logfile = logfile
        self._task_id = None

    # spawn()
    #
    # Spawns the job.
    #
    def spawn(self):

        self._tries += 1
        self._parent_start_listening()

        # Spawn the process
        self._process = _multiprocessing.AsyncioSafeProcess(target=self._child_action, args=[self._queue])

        # Block signals which are handled in the main process such that
        # the child process does not inherit the parent's state, but the main
        # process will be notified of any signal after we launch the child.
        #
        with _signals.blocked([signal.SIGINT, signal.SIGTSTP, signal.SIGTERM], ignore=False):
            with asyncio.get_child_watcher() as watcher:
                self._process.start()
                # Register the process to call `_parent_child_completed` once it is done

                # Here we delay the call to the next loop tick. This is in order to be running
                # in the main thread, as the callback itself must be thread safe.
                def on_completion(pid, returncode):
                    asyncio.get_event_loop().call_soon(self._parent_child_completed, pid, returncode)

                watcher.add_child_handler(self._process.pid, on_completion)

    # terminate()
    #
    # Politely request that an ongoing job terminate soon.
    #
    # This will send a SIGTERM signal to the Job process.
    #
    def terminate(self):

        # First resume the job if it's suspended
        self.resume(silent=True)

        self.message(MessageType.STATUS, "{} terminating".format(self.action_name))

        # Make sure there is no garbage on the queue
        self._parent_stop_listening()

        # Terminate the process using multiprocessing API pathway
        self._process.terminate()

        self._terminated = True

    # get_terminated()
    #
    # Check if a job has been terminated.
    #
    # Returns:
    #     (bool): True in the main process if Job.terminate() was called.
    #
    def get_terminated(self):
        return self._terminated

    # kill()
    #
    # Forcefully kill the process, and any children it might have.
    #
    def kill(self):
        # Force kill
        self.message(MessageType.WARN,
                     "{} did not terminate gracefully, killing".format(self.action_name))
        utils._kill_process_tree(self._process.pid)

    # suspend()
    #
    # Suspend this job.
    #
    def suspend(self):
        if not self._suspended:
            self.message(MessageType.STATUS,
                         "{} suspending".format(self.action_name))

            try:
                # Use SIGTSTP so that child processes may handle and propagate
                # it to processes they spawn that become session leaders
                os.kill(self._process.pid, signal.SIGTSTP)

                # For some reason we receive exactly one suspend event for every
                # SIGTSTP we send to the child fork(), even though the child forks
                # are setsid(). We keep a count of these so we can ignore them
                # in our event loop suspend_event()
                self._scheduler.internal_stops += 1
                self._suspended = True
            except ProcessLookupError:
                # ignore, process has already exited
                pass

    # resume()
    #
    # Resume this suspended job.
    #
    def resume(self, silent=False):
        if self._suspended:
            if not silent and not self._scheduler.terminated:
                self.message(MessageType.STATUS,
                             "{} resuming".format(self.action_name))

            os.kill(self._process.pid, signal.SIGCONT)
            self._suspended = False

    # set_task_id()
    #
    # This is called by Job subclasses to set a plugin ID
    # associated with the task at large (if any element is related
    # to the task).
    #
    # The task ID helps keep messages in the frontend coherent
    # in the case that multiple plugins log in the context of
    # a single task (e.g. running integration commands should appear
    # in the frontend for the element being built, not the element
    # running the integration commands).
    #
    # Args:
    #     task_id (int): The plugin identifier for this task
    #
    def set_task_id(self, task_id):
        self._task_id = task_id

    # send_message()
    #
    # To be called from inside Job.child_process() implementations
    # to send messages to the main process during processing.
    #
    # These messages will be processed by the class's Job.handle_message()
    # implementation.
    #
    def send_message(self, message_type, message):
        self._queue.put(_Envelope(message_type, message))

    #######################################################
    #                  Abstract Methods                   #
    #######################################################

    # handle_message()
    #
    # Handle a custom message. This will be called in the main process in
    # response to any messages sent to the main proces using the
    # Job.send_message() API from inside a Job.child_process() implementation
    #
    # Args:
    #    message_type (str): A string to identify the message type
    #    message (any): A simple serializable object
    #
    # Returns:
    #    (bool): Should return a truthy value if message_type is handled.
    #
    def handle_message(self, message_type, message):
        return False

    # parent_complete()
    #
    # This will be executed after the job finishes, and is expected to
    # pass the result to the main thread.
    #
    # Args:
    #    status (JobStatus): The job exit status
    #    result (any): The result returned by child_process().
    #
    def parent_complete(self, status, result):
        raise ImplError("Job '{kind}' does not implement parent_complete()"
                        .format(kind=type(self).__name__))

    # child_process()
    #
    # This will be executed after fork(), and is intended to perform
    # the job's task.
    #
    # Returns:
    #    (any): A (simple!) object to be returned to the main thread
    #           as the result.
    #
    def child_process(self):
        raise ImplError("Job '{kind}' does not implement child_process()"
                        .format(kind=type(self).__name__))

    # message():
    #
    # Logs a message, this will be logged in the task's logfile and
    # conditionally also be sent to the frontend.
    #
    # Args:
    #    message_type (MessageType): The type of message to send
    #    message (str): The message
    #    kwargs: Remaining Message() constructor arguments
    #
    def message(self, message_type, message, **kwargs):
        args = dict(kwargs)
        args['scheduler'] = True
        self._scheduler.context.message(Message(None, message_type, message, **args))

    # child_process_data()
    #
    # Abstract method to retrieve additional data that should be
    # returned to the parent process. Note that the job result is
    # retrieved independently.
    #
    # Values can later be retrieved in Job.child_data.
    #
    # Returns:
    #    (dict) A dict containing values to be reported to the main process
    #
    def child_process_data(self):
        return {}

    #######################################################
    #                  Local Private Methods              #
    #######################################################
    #
    # Methods prefixed with the word 'child' take place in the child process
    #
    # Methods prefixed with the word 'parent' take place in the parent process
    #
    # Other methods can be called in both child or parent processes
    #
    #######################################################

    # _child_action()
    #
    # Perform the action in the child process, this calls the action_cb.
    #
    # Args:
    #    queue (multiprocessing.Queue): The message queue for IPC
    #
    def _child_action(self, queue):

        # This avoids some SIGTSTP signals from grandchildren
        # getting propagated up to the master process
        os.setsid()

        # First set back to the default signal handlers for the signals
        # we handle, and then clear their blocked state.
        #
        signal_list = [signal.SIGTSTP, signal.SIGTERM]
        for sig in signal_list:
            signal.signal(sig, signal.SIG_DFL)
        signal.pthread_sigmask(signal.SIG_UNBLOCK, signal_list)

        # Assign the queue we passed across the process boundaries
        #
        # Set the global message handler in this child
        # process to forward messages to the parent process
        self._queue = queue
        self._scheduler.context.set_message_handler(self._child_message_handler)

        starttime = datetime.datetime.now()
        stopped_time = None

        def stop_time():
            nonlocal stopped_time
            stopped_time = datetime.datetime.now()

        def resume_time():
            nonlocal stopped_time
            nonlocal starttime
            starttime += (datetime.datetime.now() - stopped_time)

        # Time, log and and run the action function
        #
        with _signals.suspendable(stop_time, resume_time), \
            self._scheduler.context.recorded_messages(self._logfile) as filename:

            self.message(MessageType.START, self.action_name, logfile=filename)

            try:
                # Try the task action
                result = self.child_process()
            except SkipJob as e:
                elapsed = datetime.datetime.now() - starttime
                self.message(MessageType.SKIPPED, str(e),
                             elapsed=elapsed, logfile=filename)

                # Alert parent of skip by return code
                self._child_shutdown(RC_SKIPPED)
            except BstError as e:
                elapsed = datetime.datetime.now() - starttime
                self._retry_flag = e.temporary

                if self._retry_flag and (self._tries <= self._max_retries):
                    self.message(MessageType.FAIL,
                                 "Try #{} failed, retrying".format(self._tries),
                                 elapsed=elapsed, logfile=filename)
                else:
                    self.message(MessageType.FAIL, str(e),
                                 elapsed=elapsed, detail=e.detail,
                                 logfile=filename, sandbox=e.sandbox)

                self._queue.put(_Envelope('child_data', self.child_process_data()))

                # Report the exception to the parent (for internal testing purposes)
                self._child_send_error(e)

                # Set return code based on whether or not the error was temporary.
                #
                self._child_shutdown(RC_FAIL if self._retry_flag else RC_PERM_FAIL)

            except Exception as e:                        # pylint: disable=broad-except

                # If an unhandled (not normalized to BstError) occurs, that's a bug,
                # send the traceback and formatted exception back to the frontend
                # and print it to the log file.
                #
                elapsed = datetime.datetime.now() - starttime
                detail = "An unhandled exception occured:\n\n{}".format(traceback.format_exc())

                self.message(MessageType.BUG, self.action_name,
                             elapsed=elapsed, detail=detail,
                             logfile=filename)
                # Unhandled exceptions should permenantly fail
                self._child_shutdown(RC_PERM_FAIL)

            else:
                # No exception occurred in the action
                self._queue.put(_Envelope('child_data', self.child_process_data()))
                self._child_send_result(result)

                elapsed = datetime.datetime.now() - starttime
                self.message(MessageType.SUCCESS, self.action_name, elapsed=elapsed,
                             logfile=filename)

                # Shutdown needs to stay outside of the above context manager,
                # make sure we dont try to handle SIGTERM while the process
                # is already busy in sys.exit()
                self._child_shutdown(RC_OK)

    # _child_send_error()
    #
    # Sends an error to the main process through the message queue
    #
    # Args:
    #    e (Exception): The error to send
    #
    def _child_send_error(self, e):
        domain = None
        reason = None

        if isinstance(e, BstError):
            domain = e.domain
            reason = e.reason

        envelope = _Envelope('error', {
            'domain': domain,
            'reason': reason
        })
        self._queue.put(envelope)

    # _child_send_result()
    #
    # Sends the serialized result to the main process through the message queue
    #
    # Args:
    #    result (object): A simple serializable object, or None
    #
    # Note: If None is passed here, nothing needs to be sent, the
    #       result member in the parent process will simply remain None.
    #
    def _child_send_result(self, result):
        if result is not None:
            envelope = _Envelope('result', result)
            self._queue.put(envelope)

    # _child_shutdown()
    #
    # Shuts down the child process by cleaning up and exiting the process
    #
    # Args:
    #    exit_code (int): The exit code to exit with
    #
    def _child_shutdown(self, exit_code):
        self._queue.close()
        sys.exit(exit_code)

    # _child_message_handler()
    #
    # A Context delegate for handling messages, this replaces the
    # frontend's main message handler in the context of a child task
    # and performs local logging to the local log file before sending
    # the message back to the parent process for further propagation.
    #
    # Args:
    #    message (Message): The message to log
    #    context (Context): The context object delegating this message
    #
    def _child_message_handler(self, message, context):

        message.action_name = self.action_name
        message.task_id = self._task_id

        # Send to frontend if appropriate
        if context.silent_messages() and (message.message_type not in unconditional_messages):
            return

        if message.message_type == MessageType.LOG:
            return

        self._queue.put(_Envelope('message', message))

    # _parent_shutdown()
    #
    # Shuts down the Job on the parent side by reading any remaining
    # messages on the message queue and cleaning up any resources.
    #
    def _parent_shutdown(self):
        # Make sure we've read everything we need and then stop listening
        self._parent_process_queue()
        self._parent_stop_listening()

    # _parent_child_completed()
    #
    # Called in the main process courtesy of asyncio's ChildWatcher.add_child_handler()
    #
    # Args:
    #    pid (int): The PID of the child which completed
    #    returncode (int): The return code of the child process
    #
    def _parent_child_completed(self, pid, returncode):
        self._parent_shutdown()

        # We don't want to retry if we got OK or a permanent fail.
        # This is set in _child_action but must also be set for the parent.
        #
        self._retry_flag = returncode == RC_FAIL

        if self._retry_flag and (self._tries <= self._max_retries) and not self._scheduler.terminated:
            self.spawn()
            return

        # Resolve the outward facing overall job completion status
        #
        if returncode == RC_OK:
            status = JobStatus.OK
        elif returncode == RC_SKIPPED:
            status = JobStatus.SKIPPED
        elif returncode in (RC_FAIL, RC_PERM_FAIL):
            status = JobStatus.FAIL
        else:
            status = JobStatus.FAIL

        self.parent_complete(status, self._result)
        self._scheduler.job_completed(self, status)

    # _parent_process_envelope()
    #
    # Processes a message Envelope deserialized form the message queue.
    #
    # this will have the side effect of assigning some local state
    # on the Job in the parent process for later inspection when the
    # child process completes.
    #
    # Args:
    #    envelope (Envelope): The message envelope
    #
    def _parent_process_envelope(self, envelope):
        if not self._listening:
            return

        if envelope.message_type == 'message':
            # Propagate received messages from children
            # back through the context.
            self._scheduler.context.message(envelope.message)
        elif envelope.message_type == 'error':
            # For regression tests only, save the last error domain / reason
            # reported from a child task in the main process, this global state
            # is currently managed in _exceptions.py
            set_last_task_error(envelope.message['domain'],
                                envelope.message['reason'])
        elif envelope.message_type == 'result':
            assert self._result is None
            self._result = envelope.message
        elif envelope.message_type == 'child_data':
            # If we retry a job, we assign a new value to this
            self.child_data = envelope.message

        # Try Job subclass specific messages now
        elif not self.handle_message(envelope.message_type,
                                     envelope.message):
            assert 0, "Unhandled message type '{}': {}" \
                .format(envelope.message_type, envelope.message)

    # _parent_process_queue()
    #
    # Reads back message envelopes from the message queue
    # in the parent process.
    #
    def _parent_process_queue(self):
        while not self._queue.empty():
            envelope = self._queue.get_nowait()
            self._parent_process_envelope(envelope)

    # _parent_recv()
    #
    # A callback to handle I/O events from the message
    # queue file descriptor in the main process message loop
    #
    def _parent_recv(self, *args):
        self._parent_process_queue()

    # _parent_start_listening()
    #
    # Starts listening on the message queue
    #
    def _parent_start_listening(self):
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
        if not self._listening:
            self._scheduler.loop.add_reader(
                self._queue._reader.fileno(), self._parent_recv)
            self._listening = True

    # _parent_stop_listening()
    #
    # Stops listening on the message queue
    #
    def _parent_stop_listening(self):
        if self._listening:
            self._scheduler.loop.remove_reader(self._queue._reader.fileno())
            self._listening = False
