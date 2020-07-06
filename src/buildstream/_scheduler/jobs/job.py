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
import asyncio
import datetime
import multiprocessing
import os
import signal
import sys
import traceback

# BuildStream toplevel imports
from ..._exceptions import ImplError, BstError, set_last_task_error, SkipJob
from ..._message import Message, MessageType, unconditional_messages
from ...types import FastEnum
from ... import _signals, utils
from .. import _multiprocessing


# Return code values shutdown of job handling child processes
#
class _ReturnCode(FastEnum):
    OK = 0
    FAIL = 1
    PERM_FAIL = 2
    SKIPPED = 3
    TERMINATED = 4
    KILLED = -9


# JobStatus:
#
# The job completion status, passed back through the
# complete callbacks.
#
class JobStatus(FastEnum):
    # Job succeeded
    OK = 0

    # A temporary BstError was raised
    FAIL = 1

    # A SkipJob was raised
    SKIPPED = 3


# Used to distinguish between status messages and return values
class _Envelope:
    def __init__(self, message_type, message):
        self.message_type = message_type
        self.message = message


class _MessageType(FastEnum):
    LOG_MESSAGE = 1
    ERROR = 2
    RESULT = 3
    CHILD_DATA = 4
    SUBCLASS_CUSTOM_MESSAGE = 5


# Job()
#
# The Job object represents a task that will run in parallel to the main
# process. It has some methods that are not implemented - they are meant for
# you to implement in a subclass.
#
# It has a close relationship with the ChildJob class, and it can be considered
# a two part solution:
#
# 1. A Job instance, which will create a ChildJob instance and arrange for
#    childjob.child_process() to be executed in another process.
# 2. The created ChildJob instance, which does the actual work.
#
# This split makes it clear what data is passed to the other process and what
# is executed in which process.
#
# To set up a minimal new kind of Job, e.g. YourJob:
#
# 1. Create a YourJob class, inheriting from Job.
# 2. Create a YourChildJob class, inheriting from ChildJob.
# 3. Implement YourJob.create_child_job() and YourJob.parent_complete().
# 4. Implement YourChildJob.child_process().
#
# A Job instance and its ChildJob share a message pipe. You may send custom
# messages to the main process using YourChildJob.send_message(). Such messages
# must be processed in YourJob.handle_message(), which you will also need to
# override for this purpose.
#
# Args:
#    scheduler (Scheduler): The scheduler
#    action_name (str): The queue action name
#    logfile (str): A template string that points to the logfile
#                   that should be used - should contain {pid}.
#    max_retries (int): The maximum number of retries
#
class Job:
    def __init__(self, scheduler, action_name, logfile, *, max_retries=0):

        #
        # Public members
        #
        self.name = None  # The name of the job, set by the job's subclass
        self.action_name = action_name  # The action name for the Queue
        self.child_data = None  # Data to be sent to the main process

        #
        # Private members
        #
        self._scheduler = scheduler  # The scheduler
        self._messenger = self._scheduler.context.messenger
        self._pipe_r = None  # The read end of a pipe for message passing
        self._process = None  # The Process object
        self._listening = False  # Whether the parent is currently listening
        self._suspended = False  # Whether this job is currently suspended
        self._max_retries = max_retries  # Maximum number of automatic retries
        self._result = None  # Return value of child action in the parent
        self._tries = 0  # Try count, for retryable jobs
        self._terminated = False  # Whether this job has been explicitly terminated

        self._logfile = logfile
        self._message_element_name = None  # The plugin instance element name for messaging
        self._message_element_key = None  # The element key for messaging
        self._element = None  # The Element() passed to the Job() constructor, if applicable

    # set_name()
    #
    # Sets the name of this job
    def set_name(self, name):
        self.name = name

    # start()
    #
    # Starts the job.
    #
    def start(self):

        assert not self._terminated, "Attempted to start process which was already terminated"

        self._pipe_r, pipe_w = multiprocessing.Pipe(duplex=False)

        self._tries += 1
        self._parent_start_listening()

        child_job = self.create_child_job(  # pylint: disable=assignment-from-no-return
            self.action_name,
            self._messenger,
            self._scheduler.context.logdir,
            self._logfile,
            self._max_retries,
            self._tries,
            self._message_element_name,
            self._message_element_key,
        )

        self._process = _multiprocessing.AsyncioSafeProcess(target=child_job.child_action, args=[pipe_w],)

        # Block signals which are handled in the main process such that
        # the child process does not inherit the parent's state, but the main
        # process will be notified of any signal after we launch the child.
        #
        with _signals.blocked([signal.SIGINT, signal.SIGTSTP, signal.SIGTERM], ignore=False):
            with asyncio.get_child_watcher() as watcher:
                self._process.start()
                # Register the process to call `_parent_child_completed` once it is done

                # Close the write end of the pipe in the parent
                pipe_w.close()

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

        # Make sure there is no garbage on the pipe
        self._parent_stop_listening()

        # Terminate the process using multiprocessing API pathway
        if self._process:
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
        self.message(MessageType.WARN, "{} did not terminate gracefully, killing".format(self.action_name))
        if self._process:
            utils._kill_process_tree(self._process.pid)

    # suspend()
    #
    # Suspend this job.
    #
    def suspend(self):
        if not self._suspended:
            self.message(MessageType.STATUS, "{} suspending".format(self.action_name))

            try:
                # Use SIGTSTP so that child processes may handle and propagate
                # it to processes they start that become session leaders.
                os.kill(self._process.pid, signal.SIGTSTP)

                # For some reason we receive exactly one suspend event for
                # every SIGTSTP we send to the child process, even though the
                # child processes are setsid(). We keep a count of these so we
                # can ignore them in our event loop suspend_event().
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
                self.message(MessageType.STATUS, "{} resuming".format(self.action_name))

            os.kill(self._process.pid, signal.SIGCONT)
            self._suspended = False

    # set_message_element_name()
    #
    # This is called by Job subclasses to set the plugin instance element
    # name issuing the message (if an element is related to the Job).
    #
    # Args:
    #     element_name (int): The element_name to be supplied to the Message() constructor
    #
    def set_message_element_name(self, element_name):
        self._message_element_name = element_name

    # set_message_element_key()
    #
    # This is called by Job subclasses to set the element
    # key for for the issuing message (if an element is related to the Job).
    #
    # Args:
    #     element_key (tuple): The element_key tuple to be supplied to the Message() constructor
    #
    def set_message_element_key(self, element_key):
        self._message_element_key = element_key

    # message():
    #
    # Logs a message, this will be logged in the task's logfile and
    # conditionally also be sent to the frontend.
    #
    # XXX: Note no calls to message() currently override the default
    #      name & key (previously unique_id), potential to be removed.
    #
    # Args:
    #    message_type (MessageType): The type of message to send
    #    message (str): The message
    #    kwargs: Remaining Message() constructor arguments, note that you can
    #            override 'element_name' and 'element_key' this way.
    #
    def message(self, message_type, message, element_name=None, element_key=None, **kwargs):
        kwargs["scheduler"] = True
        # If default name & key values not provided, set as given job attributes
        if element_name is None:
            element_name = self._message_element_name
        if element_key is None:
            element_key = self._message_element_key
        message = Message(message_type, message, element_name=element_name, element_key=element_key, **kwargs)
        self._messenger.message(message)

    # get_element()
    #
    # Get the Element() related to the job, if jobtype (i.e ElementJob) is
    # applicable, default None.
    #
    # Returns:
    #     (Element): The Element() instance pertaining to the Job, else None.
    #
    def get_element(self):
        return self._element

    #######################################################
    #                  Abstract Methods                   #
    #######################################################

    # handle_message()
    #
    # Handle a custom message. This will be called in the main process in
    # response to any messages sent to the main process using the
    # Job.send_message() API from inside a Job.child_process() implementation.
    #
    # There is no need to implement this function if no custom messages are
    # expected.
    #
    # Args:
    #    message (any): A simple object (must be pickle-able, i.e. strings,
    #                   lists, dicts, numbers, but not Element instances).
    #
    def handle_message(self, message):
        raise ImplError("Job '{kind}' does not implement handle_message()".format(kind=type(self).__name__))

    # parent_complete()
    #
    # This will be executed in the main process after the job finishes, and is
    # expected to pass the result to the main thread.
    #
    # Args:
    #    status (JobStatus): The job exit status
    #    result (any): The result returned by child_process().
    #
    def parent_complete(self, status, result):
        raise ImplError("Job '{kind}' does not implement parent_complete()".format(kind=type(self).__name__))

    # create_child_job()
    #
    # Called by a Job instance to create a child job.
    #
    # The child job object is an instance of a subclass of ChildJob.
    #
    # The child job object's child_process() method will be executed in another
    # process, so that work is done in parallel. See the documentation for the
    # Job class for more information on this relationship.
    #
    # This method must be overridden by Job subclasses.
    #
    # Returns:
    #    (ChildJob): An instance of a subclass of ChildJob.
    #
    def create_child_job(self, *args, **kwargs):
        raise ImplError("Job '{kind}' does not implement create_child_job()".format(kind=type(self).__name__))

    #######################################################
    #                  Local Private Methods              #
    #######################################################

    # _parent_shutdown()
    #
    # Shuts down the Job on the parent side by reading any remaining
    # messages on the message pipe and cleaning up any resources.
    #
    def _parent_shutdown(self):
        # Make sure we've read everything we need and then stop listening
        self._parent_process_pipe()
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

        try:
            returncode = _ReturnCode(returncode)
        except ValueError:
            # An unexpected return code was returned; fail permanently and report
            self.message(
                MessageType.ERROR,
                "Internal job process unexpectedly died with exit code {}".format(returncode),
                logfile=self._logfile,
            )
            returncode = _ReturnCode.PERM_FAIL

        # We don't want to retry if we got OK or a permanent fail.
        retry_flag = returncode == _ReturnCode.FAIL

        if retry_flag and (self._tries <= self._max_retries) and not self._scheduler.terminated:
            self.start()
            return

        # Resolve the outward facing overall job completion status
        #
        if returncode == _ReturnCode.OK:
            status = JobStatus.OK
        elif returncode == _ReturnCode.SKIPPED:
            status = JobStatus.SKIPPED
        elif returncode in (_ReturnCode.FAIL, _ReturnCode.PERM_FAIL):
            status = JobStatus.FAIL
        elif returncode == _ReturnCode.TERMINATED:
            if self._terminated:
                self.message(MessageType.INFO, "Process was terminated")
            else:
                self.message(MessageType.ERROR, "Process was terminated unexpectedly")

            status = JobStatus.FAIL
        elif returncode == _ReturnCode.KILLED:
            if self._terminated:
                self.message(MessageType.INFO, "Process was killed")
            else:
                self.message(MessageType.ERROR, "Process was killed unexpectedly")

            status = JobStatus.FAIL
        else:
            status = JobStatus.FAIL

        self.parent_complete(status, self._result)
        self._scheduler.job_completed(self, status)

        # Force the deletion of the pipe and process objects to try and clean up FDs
        self._pipe_r.close()
        self._pipe_r = self._process = None

    # _parent_process_envelope()
    #
    # Processes a message Envelope deserialized form the message pipe.
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

        if envelope.message_type is _MessageType.LOG_MESSAGE:
            # Propagate received messages from children
            # back through the context.
            self._messenger.message(envelope.message)
        elif envelope.message_type is _MessageType.ERROR:
            # For regression tests only, save the last error domain / reason
            # reported from a child task in the main process, this global state
            # is currently managed in _exceptions.py
            set_last_task_error(envelope.message["domain"], envelope.message["reason"])
        elif envelope.message_type is _MessageType.RESULT:
            assert self._result is None
            self._result = envelope.message
        elif envelope.message_type is _MessageType.CHILD_DATA:
            # If we retry a job, we assign a new value to this
            self.child_data = envelope.message
        elif envelope.message_type is _MessageType.SUBCLASS_CUSTOM_MESSAGE:
            self.handle_message(envelope.message)
        else:
            assert False, "Unhandled message type '{}': {}".format(envelope.message_type, envelope.message)

    # _parent_process_pipe()
    #
    # Reads back message envelopes from the message pipe
    # in the parent process.
    #
    def _parent_process_pipe(self):
        while self._pipe_r.poll():
            try:
                envelope = self._pipe_r.recv()
            except EOFError:
                self._parent_stop_listening()
                break
            self._parent_process_envelope(envelope)

    # _parent_recv()
    #
    # A callback to handle I/O events from the message
    # pipe file descriptor in the main process message loop
    #
    def _parent_recv(self, *args):
        self._parent_process_pipe()

    # _parent_start_listening()
    #
    # Starts listening on the message pipe
    #
    def _parent_start_listening(self):
        if not self._listening:
            self._scheduler.loop.add_reader(self._pipe_r.fileno(), self._parent_recv)
            self._listening = True

    # _parent_stop_listening()
    #
    # Stops listening on the message pipe
    #
    def _parent_stop_listening(self):
        if self._listening:
            self._scheduler.loop.remove_reader(self._pipe_r.fileno())
            self._listening = False


# ChildJob()
#
# The ChildJob object represents the part of a parallel task that will run in a
# separate process. It has a close relationship with the parent Job that
# created it.
#
# See the documentation of the Job class for more on their relationship, and
# how to set up a (Job, ChildJob pair).
#
# The args below are passed from the parent Job to the ChildJob.
#
# Args:
#    scheduler (Scheduler): The scheduler.
#    action_name (str): The queue action name.
#    logfile (str): A template string that points to the logfile
#                   that should be used - should contain {pid}.
#    max_retries (int): The maximum number of retries.
#    tries (int): The number of retries so far.
#    message_element_name (str): None, or the plugin instance element name
#                                to be supplied to the Message() constructor.
#    message_element_key (tuple): None, or the element display key tuple
#                                to be supplied to the Message() constructor.
#
class ChildJob:
    def __init__(
        self, action_name, messenger, logdir, logfile, max_retries, tries, message_element_name, message_element_key
    ):

        self.action_name = action_name

        self._messenger = messenger
        self._logdir = logdir
        self._logfile = logfile
        self._max_retries = max_retries
        self._tries = tries
        self._message_element_name = message_element_name
        self._message_element_key = message_element_key

        self._pipe_w = None  # The write end of a pipe for message passing

    # message():
    #
    # Logs a message, this will be logged in the task's logfile and
    # conditionally also be sent to the frontend.
    #
    # XXX: Note no calls to message() currently override the default
    #      name & key (previously unique_id), potential to be removed.
    #
    # Args:
    #    message_type (MessageType): The type of message to send
    #    message (str): The message
    #    kwargs: Remaining Message() constructor arguments, note
    #            element_key is set in _child_message_handler
    #            for front end display if not already set or explicitly
    #            overriden here.
    #
    def message(self, message_type, message, element_name=None, element_key=None, **kwargs):
        kwargs["scheduler"] = True
        # If default name & key values not provided, set as given job attributes
        if element_name is None:
            element_name = self._message_element_name
        if element_key is None:
            element_key = self._message_element_key
        self._messenger.message(
            Message(message_type, message, element_name=element_name, element_key=element_key, **kwargs)
        )

    # send_message()
    #
    # Send data in a message to the parent Job, running in the main process.
    #
    # This allows for custom inter-process communication between subclasses of
    # Job and ChildJob.
    #
    # These messages will be processed by the Job.handle_message()
    # implementation, which may be overridden to support one or more custom
    # 'message_type's.
    #
    # Args:
    #    message_data (any): A simple object (must be pickle-able, i.e.
    #                        strings, lists, dicts, numbers, but not Element
    #                        instances). This is sent to the parent Job.
    #
    def send_message(self, message_data):
        self._send_message(_MessageType.SUBCLASS_CUSTOM_MESSAGE, message_data)

    #######################################################
    #                  Abstract Methods                   #
    #######################################################

    # child_process()
    #
    # This will be executed after starting the child process, and is intended
    # to perform the job's task.
    #
    # Returns:
    #    (any): A simple object (must be pickle-able, i.e. strings, lists,
    #           dicts, numbers, but not Element instances). It is returned to
    #           the parent Job running in the main process. This is taken as
    #           the result of the Job.
    #
    def child_process(self):
        raise ImplError("ChildJob '{kind}' does not implement child_process()".format(kind=type(self).__name__))

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

    # child_action()
    #
    # Perform the action in the child process, this calls the action_cb.
    #
    # Args:
    #    pipe_w (multiprocessing.connection.Connection): The message pipe for IPC
    #
    def child_action(self, pipe_w):

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

        # Assign the pipe we passed across the process boundaries
        #
        # Set the global message handler in this child
        # process to forward messages to the parent process
        self._pipe_w = pipe_w
        self._messenger.set_message_handler(self._child_message_handler)

        starttime = datetime.datetime.now()
        stopped_time = None

        def stop_time():
            nonlocal stopped_time
            stopped_time = datetime.datetime.now()

        def resume_time():
            nonlocal stopped_time
            nonlocal starttime
            starttime += datetime.datetime.now() - stopped_time

        # Graciously handle sigterms.
        def handle_sigterm():
            self._child_shutdown(_ReturnCode.TERMINATED)

        # Time, log and and run the action function
        #
        with _signals.terminator(handle_sigterm), _signals.suspendable(
            stop_time, resume_time
        ), self._messenger.recorded_messages(self._logfile, self._logdir) as filename:

            self.message(MessageType.START, self.action_name, logfile=filename)

            try:
                # Try the task action
                result = self.child_process()  # pylint: disable=assignment-from-no-return
            except SkipJob as e:
                elapsed = datetime.datetime.now() - starttime
                self.message(MessageType.SKIPPED, str(e), elapsed=elapsed, logfile=filename)

                # Alert parent of skip by return code
                self._child_shutdown(_ReturnCode.SKIPPED)
            except BstError as e:
                elapsed = datetime.datetime.now() - starttime
                retry_flag = e.temporary

                if retry_flag and (self._tries <= self._max_retries):
                    self.message(
                        MessageType.FAIL,
                        "Try #{} failed, retrying".format(self._tries),
                        elapsed=elapsed,
                        logfile=filename,
                    )
                else:
                    self.message(
                        MessageType.FAIL, str(e), elapsed=elapsed, detail=e.detail, logfile=filename, sandbox=e.sandbox
                    )

                self._send_message(_MessageType.CHILD_DATA, self.child_process_data())

                # Report the exception to the parent (for internal testing purposes)
                self._child_send_error(e)

                # Set return code based on whether or not the error was temporary.
                #
                self._child_shutdown(_ReturnCode.FAIL if retry_flag else _ReturnCode.PERM_FAIL)

            except Exception:  # pylint: disable=broad-except

                # If an unhandled (not normalized to BstError) occurs, that's a bug,
                # send the traceback and formatted exception back to the frontend
                # and print it to the log file.
                #
                elapsed = datetime.datetime.now() - starttime
                detail = "An unhandled exception occured:\n\n{}".format(traceback.format_exc())

                self.message(MessageType.BUG, self.action_name, elapsed=elapsed, detail=detail, logfile=filename)
                # Unhandled exceptions should permenantly fail
                self._child_shutdown(_ReturnCode.PERM_FAIL)

            else:
                # No exception occurred in the action
                self._send_message(_MessageType.CHILD_DATA, self.child_process_data())
                self._child_send_result(result)

                elapsed = datetime.datetime.now() - starttime
                self.message(MessageType.SUCCESS, self.action_name, elapsed=elapsed, logfile=filename)

                # Shutdown needs to stay outside of the above context manager,
                # make sure we dont try to handle SIGTERM while the process
                # is already busy in sys.exit()
                self._child_shutdown(_ReturnCode.OK)

    #######################################################
    #                  Local Private Methods              #
    #######################################################

    # _send_message()
    #
    # Send data in a message to the parent Job, running in the main process.
    #
    # Args:
    #    message_type (str): The type of message to send.
    #    message_data (any): A simple object (must be pickle-able, i.e.
    #                        strings, lists, dicts, numbers, but not Element
    #                        instances). This is sent to the parent Job.
    #
    def _send_message(self, message_type, message_data):
        self._pipe_w.send(_Envelope(message_type, message_data))

    # _child_send_error()
    #
    # Sends an error to the main process through the message pipe
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

        self._send_message(_MessageType.ERROR, {"domain": domain, "reason": reason})

    # _child_send_result()
    #
    # Sends the serialized result to the main process through the message pipe
    #
    # Args:
    #    result (any): None, or a simple object (must be pickle-able, i.e.
    #                  strings, lists, dicts, numbers, but not Element
    #                  instances).
    #
    # Note: If None is passed here, nothing needs to be sent, the
    #       result member in the parent process will simply remain None.
    #
    def _child_send_result(self, result):
        if result is not None:
            self._send_message(_MessageType.RESULT, result)

    # _child_shutdown()
    #
    # Shuts down the child process by cleaning up and exiting the process
    #
    # Args:
    #    exit_code (_ReturnCode): The exit code to exit with
    #
    def _child_shutdown(self, exit_code):
        self._pipe_w.close()
        assert isinstance(exit_code, _ReturnCode)
        sys.exit(exit_code.value)

    # _child_message_handler()
    #
    # A Context delegate for handling messages, this replaces the
    # frontend's main message handler in the context of a child task
    # and performs local logging to the local log file before sending
    # the message back to the parent process for further propagation.
    # The related element display key is added to the message for
    # widget rendering if not already set for an element childjob.
    #
    # Args:
    #    message     (Message): The message to log
    #    is_silenced (bool)   : Whether messages are silenced
    #
    def _child_message_handler(self, message, is_silenced):

        message.action_name = self.action_name

        # If no key has been set at this point, and the element job has
        # a related key, set it. This is needed for messages going
        # straight to the message handler from the child process.
        if message.element_key is None and self._message_element_key:
            message.element_key = self._message_element_key

        # Send to frontend if appropriate
        if is_silenced and (message.message_type not in unconditional_messages):
            return

        if message.message_type == MessageType.LOG:
            return

        self._send_message(_MessageType.LOG_MESSAGE, message)
