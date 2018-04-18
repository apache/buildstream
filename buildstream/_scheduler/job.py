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
from ruamel import yaml

# BuildStream toplevel imports
from .._exceptions import BstError, set_last_task_error
from .._message import Message, MessageType, unconditional_messages
from ..plugin import _plugin_lookup
from .. import _signals, utils


# Used to distinguish between status messages and return values
class Envelope():
    def __init__(self, message_type, message):
        self.message_type = message_type
        self.message = message


# Process class that doesn't call waitpid on its own.
# This prevents conflicts with the asyncio child watcher.
class Process(multiprocessing.Process):
    def start(self):
        self._popen = self._Popen(self)
        self._sentinel = self._popen.sentinel


# Job()
#
# The Job object represents a parallel task, when calling Job.spawn(),
# the given `action_cb` will be called in parallel to the calling process,
# and `complete_cb` will be called with the action result in the calling
# process when the job completes.
#
# Args:
#    scheduler (Scheduler): The scheduler
#    element (Element): The element to operate on
#    action_name (str): The queue action name
#    action_cb (callable): The action function
#    complete_cb (callable): The function to call when complete
#    max_retries (int): The maximum number of retries
#
# Here is the calling signature of the action_cb:
#
#     action_cb():
#
#     This function will be called in the child task
#
#     Args:
#        element (Element): The element passed to the Job() constructor
#
#     Returns:
#        (object): Any abstract simple python object, including a string, int,
#                  bool, list or dict, this must be a simple serializable object.
#
# Here is the calling signature of the complete_cb:
#
#     complete_cb():
#
#     This function will be called when the child task completes
#
#     Args:
#        job (Job): The job object which completed
#        element (Element): The element passed to the Job() constructor
#        success (bool): True if the action_cb did not raise an exception
#        result (object): The deserialized object returned by the `action_cb`, or None
#                         if `success` is False
#
class Job():

    def __init__(self, scheduler, element, action_name, action_cb, complete_cb, *, max_retries=0):

        #
        # Public members
        #
        self.element = element           # The element we're processing
        self.action_name = action_name   # The action name for the Queue
        self.workspace_dict = None       # A serialized Workspace object, after any modifications

        #
        # Private members
        #
        self._scheduler = scheduler            # The scheduler
        self._queue = multiprocessing.Queue()  # A message passing queue
        self._process = None                   # The Process object
        self._watcher = None                   # Child process watcher
        self._action_cb = action_cb            # The action callable function
        self._complete_cb = complete_cb        # The complete callable function
        self._listening = False                # Whether the parent is currently listening
        self._suspended = False                # Whether this job is currently suspended
        self._max_retries = max_retries        # Maximum number of automatic retries
        self._result = None                    # Return value of child action in the parent
        self._tries = 0                        # Try count, for retryable jobs

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

        self._message(self.element, MessageType.STATUS,
                      "{} terminating".format(self.action_name))

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
        self._message(self.element, MessageType.WARN,
                      "{} did not terminate gracefully, killing".format(self.action_name))
        utils._kill_process_tree(self._process.pid)

    # suspend()
    #
    # Suspend this job.
    #
    def suspend(self):
        if not self._suspended:
            self._message(self.element, MessageType.STATUS,
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
                self._message(self.element, MessageType.STATUS,
                              "{} resuming".format(self.action_name))

            os.kill(self._process.pid, signal.SIGCONT)
            self._suspended = False

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

    # _message():
    #
    # Sends a message to the frontend
    #
    # Args:
    #    plugin (Plugin): The plugin to send a message for
    #    message_type (MessageType): The type of message to send
    #    message (str): The message
    #    kwargs: Remaining Message() constructor arguments
    #
    def _message(self, plugin, message_type, message, **kwargs):
        args = dict(kwargs)
        args['scheduler'] = True
        self._scheduler.context.message(
            Message(plugin._get_unique_id(),
                    message_type,
                    message,
                    **args))

    # _child_action()
    #
    # Perform the action in the child process, this calls the action_cb.
    #
    # Args:
    #    queue (multiprocessing.Queue): The message queue for IPC
    #
    def _child_action(self, queue):

        element = self.element

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
            element._logging_enabled(self.action_name) as filename:

            self._message(element, MessageType.START, self.action_name, logfile=filename)

            # Print the element's environment at the beginning of any element's log file.
            #
            # This should probably be omitted for non-build tasks but it's harmless here
            elt_env = element.get_environment()
            env_dump = yaml.round_trip_dump(elt_env, default_flow_style=False, allow_unicode=True)
            self._message(element, MessageType.LOG,
                          "Build environment for element {}".format(element.name),
                          detail=env_dump, logfile=filename)

            try:
                # Try the task action
                result = self._action_cb(element)
            except BstError as e:
                elapsed = datetime.datetime.now() - starttime

                if self._tries <= self._max_retries:
                    self._message(element, MessageType.FAIL, "Try #{} failed, retrying".format(self._tries),
                                  elapsed=elapsed)
                else:
                    self._message(element, MessageType.FAIL, str(e),
                                  elapsed=elapsed, detail=e.detail,
                                  logfile=filename, sandbox=e.sandbox)

                # Report changes in the workspace, even if there was a handled failure
                self._child_send_workspace()

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
                self._message(element, MessageType.BUG, self.action_name,
                              elapsed=elapsed, detail=detail,
                              logfile=filename)
                self._child_shutdown(1)

            else:
                # No exception occurred in the action
                self._child_send_workspace()
                self._child_send_result(result)

                elapsed = datetime.datetime.now() - starttime
                self._message(element, MessageType.SUCCESS, self.action_name, elapsed=elapsed,
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

    # _child_send_workspace()
    #
    # Sends the serialized workspace through the message queue, if any
    #
    def _child_send_workspace(self):
        workspace = self.element._get_workspace()
        if workspace:
            envelope = Envelope('workspace', workspace.to_dict())
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

    # _child_log()
    #
    # Logs a Message to the process's dedicated log file
    #
    # Args:
    #    plugin (Plugin): The plugin to log for
    #    message (Message): The message to log
    #
    def _child_log(self, plugin, message):

        with plugin._output_file() as output:
            INDENT = "    "
            EMPTYTIME = "--:--:--"

            name = '[' + plugin.name + ']'

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

        # Tag them on the way out the door...
        message.action_name = self.action_name
        message.task_id = self.element._get_unique_id()

        # Use the plugin for the task for the output, not a plugin
        # which might be acting on behalf of the task
        plugin = _plugin_lookup(message.task_id)

        # Log first
        self._child_log(plugin, message)

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

        self._complete_cb(self, self.element, returncode == 0, self._result)

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
        elif envelope.message_type == 'workspace':
            self.workspace_dict = envelope.message
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
