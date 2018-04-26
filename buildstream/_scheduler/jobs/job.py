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
import sys
import signal
import datetime
import traceback
import asyncio
import multiprocessing
from contextlib import contextmanager

import psutil

# BuildStream toplevel imports
from ..._exceptions import ImplError, BstError, set_last_task_error
from ..._message import MessageType, unconditional_messages
from ... import _signals, utils


# Used to distinguish between status messages and return values
class Envelope():
    def __init__(self, message_type, message):
        self._message_type = message_type
        self._message = message


# Process class that doesn't call waitpid on its own.
# This prevents conflicts with the asyncio child watcher.
class Process(multiprocessing.Process):
    # pylint: disable=attribute-defined-outside-init
    def start(self):
        self._popen = self._Popen(self)
        self._sentinel = self._popen.sentinel


# Job()
#
# The Job object represents a parallel task, when calling Job.spawn(),
# the given `Job._child_process` will be called in parallel to the
# calling process, and `Job._parent_complete` will be called with the
# action result in the calling process when the job completes.
#
# Args:
#    scheduler (Scheduler): The scheduler
#    action_name (str): The queue action name
#    max_retries (int): The maximum number of retries
#
class Job():

    def __init__(self, scheduler, job_type, action_name, logfile, *, max_retries=0):

        #
        # Public members
        #
        self.action_name = action_name   # The action name for the Queue
        self.child_data = None           # Data to be sent to the main process
        self.job_type = job_type         # The type of the job

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
        self._logfile = logfile

    # spawn()
    #
    # Spawns the job.
    #
    def spawn(self):

        self._tries += 1
        self._parent_start_listening()

        # Spawn the process
        self._process = Process(target=self._child_action, args=[self._queue])

        # Block signals which are handled in the main process such that
        # the child process does not inherit the parent's state, but the main
        # process will be notified of any signal after we launch the child.
        #
        with _signals.blocked([signal.SIGINT, signal.SIGTSTP, signal.SIGTERM], ignore=False):
            self._process.start()

        # Wait for it to complete
        self._watcher = asyncio.get_child_watcher()
        self._watcher.add_child_handler(self._process.pid, self._parent_child_completed)

    # terminate()
    #
    # Politely request that an ongoing job terminate soon.
    #
    # This will send a SIGTERM signal to the Job process.
    #
    def terminate(self):

        # First resume the job if it's suspended
        self.resume(silent=True)

        self._message(MessageType.STATUS, "{} terminating".format(self.action_name))

        # Make sure there is no garbage on the queue
        self._parent_stop_listening()

        # Terminate the process using multiprocessing API pathway
        self._process.terminate()

    # terminate_wait()
    #
    # Wait for terminated jobs to complete
    #
    # Args:
    #    timeout (float): Seconds to wait
    #
    # Returns:
    #    (bool): True if the process terminated cleanly, otherwise False
    #
    def terminate_wait(self, timeout):

        # Join the child process after sending SIGTERM
        self._process.join(timeout)
        return self._process.exitcode is not None

    # kill()
    #
    # Forcefully kill the process, and any children it might have.
    #
    def kill(self):

        # Force kill
        self._message(MessageType.WARN,
                      "{} did not terminate gracefully, killing".format(self.action_name))

        try:
            utils._kill_process_tree(self._process.pid)
        # This can happen if the process died of its own accord before
        # we try to kill it
        except psutil.NoSuchProcess:
            return

    # suspend()
    #
    # Suspend this job.
    #
    def suspend(self):
        if not self._suspended:
            self._message(MessageType.STATUS,
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
            if not silent:
                self._message(MessageType.STATUS,
                              "{} resuming".format(self.action_name))

            os.kill(self._process.pid, signal.SIGCONT)
            self._suspended = False

    #######################################################
    #                  Abstract Methods                   #
    #######################################################
    # _parent_complete()
    #
    # This will be executed after the job finishes, and is expected to
    # pass the result to the main thread.
    #
    # Args:
    #    success (bool): Whether the job was successful.
    #    result (any): The result returned by _child_process().
    #
    def _parent_complete(self, success, result):
        raise ImplError("Job '{kind}' does not implement _parent_complete()"
                        .format(kind=type(self).__name__))

    # _child_process()
    #
    # This will be executed after fork(), and is intended to perform
    # the job's task.
    #
    # Returns:
    #    (any): A (simple!) object to be returned to the main thread
    #           as the result.
    #
    def _child_process(self):
        raise ImplError("Job '{kind}' does not implement _child_process()"
                        .format(kind=type(self).__name__))

    # _child_logging_enabled()
    #
    # Start the log for this job. This function will be given a
    # template string for the path to a log file - this will contain
    # "{pid}", which should be replaced with the current process'
    # PID. (i.e., call something like `logfile.format(pid=os.getpid())`).
    #
    # Args:
    #    logfile (str): A template string that points to the logfile
    #                   that should be used - replace {pid} first.
    #
    # Yields:
    #    (str) The path to the logfile with {pid} replaced.
    #
    @contextmanager
    def _child_logging_enabled(self, logfile):
        raise ImplError("Job '{kind}' does not implement _child_logging_enabled()"
                        .format(kind=type(self).__name__))

    # _message():
    #
    # Sends a message to the frontend
    #
    # Args:
    #    message_type (MessageType): The type of message to send
    #    message (str): The message
    #    kwargs: Remaining Message() constructor arguments
    #
    def _message(self, message_type, message, **kwargs):
        raise ImplError("Job '{kind}' does not implement _message()"
                        .format(kind=type(self).__name__))

    # _child_process_data()
    #
    # Abstract method to retrieve additional data that should be
    # returned to the parent process. Note that the job result is
    # retrieved independently.
    #
    # Values can later be retrieved in Job.child_data.
    #
    # Returns:
    #    (dict) A dict containing values later to be read by _process_sync_data
    #
    def _child_process_data(self):
        return {}

    # _child_log()
    #
    # Log a message returned by the frontend's main message handler
    # and return it to the main process.
    #
    # This method is also expected to add process-specific information
    # to the message (notably, action_name and task_id).
    #
    # Arguments:
    #     message (str): The message to log
    #
    # Returns:
    #     message (Message): A message object
    #
    def _child_log(self, message):
        raise ImplError("Job '{kind}' does not implement _child_log()"
                        .format(kind=type(self).__name__))

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

    # _format_frontend_message()
    #
    # Format a message from the frontend for logging purposes. This
    # will prepend a time code and add other information to help
    # determine what happened.
    #
    # Args:
    #    message (Message) - The message to create a text from.
    #    name (str) - A name for the executing context.
    #
    # Returns:
    #    (str) The text to log.
    #
    def _format_frontend_message(self, message, name):
        INDENT = "    "
        EMPTYTIME = "--:--:--"
        template = "[{timecode: <8}] {type: <7} {name: <15}: {message}"

        detail = ''
        if message.detail is not None:
            template += "\n\n{detail}"
            detail = message.detail.rstrip('\n')
            detail = INDENT + INDENT.join(detail.splitlines(True))

        timecode = EMPTYTIME
        if message.message_type in (MessageType.SUCCESS, MessageType.FAIL):
            hours, remainder = divmod(int(message.elapsed.total_seconds()), 60**2)
            minutes, seconds = divmod(remainder, 60)
            timecode = "{0:02d}:{1:02d}:{2:02d}".format(hours, minutes, seconds)

        return template.format(timecode=timecode,
                               type=message.message_type.upper(),
                               name=name,
                               message=message.message,
                               detail=detail)

    # _child_action()
    #
    # Perform the action in the child process, this calls the action_cb.
    #
    # Args:
    #    queue (multiprocessing.Queue): The message queue for IPC
    #
    def _child_action(self, queue):

        logfile = self._logfile

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
            self._child_logging_enabled(logfile) as filename:

            try:
                # Try the task action
                result = self._child_process()
            except BstError as e:
                elapsed = datetime.datetime.now() - starttime

                if self._tries <= self._max_retries:
                    self._message(MessageType.FAIL,
                                  "Try #{} failed, retrying".format(self._tries),
                                  elapsed=elapsed)
                else:
                    self._message(MessageType.FAIL, str(e),
                                  elapsed=elapsed, detail=e.detail,
                                  logfile=filename, sandbox=e.sandbox)

                self._queue.put(Envelope('child_data', self._child_process_data()))

                # Report the exception to the parent (for internal testing purposes)
                self._child_send_error(e)
                self._child_shutdown(1)

            except Exception as e:                        # pylint: disable=broad-except

                # If an unhandled (not normalized to BstError) occurs, that's a bug,
                # send the traceback and formatted exception back to the frontend
                # and print it to the log file.
                #
                elapsed = datetime.datetime.now() - starttime
                detail = "An unhandled exception occured:\n\n{}".format(traceback.format_exc())

                self._message(MessageType.BUG, self.action_name,
                              elapsed=elapsed, detail=detail,
                              logfile=filename)
                self._child_shutdown(1)

            else:
                # No exception occurred in the action
                self._queue.put(Envelope('child_data', self._child_process_data()))
                self._child_send_result(result)

                elapsed = datetime.datetime.now() - starttime
                self._message(MessageType.SUCCESS, self.action_name, elapsed=elapsed,
                              logfile=filename)

                # Shutdown needs to stay outside of the above context manager,
                # make sure we dont try to handle SIGTERM while the process
                # is already busy in sys.exit()
                self._child_shutdown(0)

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

        envelope = Envelope('error', {
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
            envelope = Envelope('result', result)
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

        # Log first
        message = self._child_log(message)

        if message.message_type == MessageType.FAIL and self._tries <= self._max_retries:
            # Job will be retried, display failures as warnings in the frontend
            message.message_type = MessageType.WARN

        # Send to frontend if appropriate
        if context.silent_messages() and (message.message_type not in unconditional_messages):
            return

        if message.message_type == MessageType.LOG:
            return

        self._queue.put(Envelope('message', message))

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

        if returncode != 0 and self._tries <= self._max_retries:
            self.spawn()
            return

        self._parent_complete(returncode == 0, self._result)
        self._scheduler.job_completed(self)

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

        if envelope._message_type == 'message':
            # Propagate received messages from children
            # back through the context.
            self._scheduler.context.message(envelope._message)
        elif envelope._message_type == 'error':
            # For regression tests only, save the last error domain / reason
            # reported from a child task in the main process, this global state
            # is currently managed in _exceptions.py
            set_last_task_error(envelope._message['domain'],
                                envelope._message['reason'])
        elif envelope._message_type == 'result':
            assert self._result is None
            self._result = envelope._message
        elif envelope._message_type == 'child_data':
            assert self.child_data is None
            self.child_data = envelope._message
        else:
            raise Exception()

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
