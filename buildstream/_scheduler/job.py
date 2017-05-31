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
from ..exceptions import _BstError
from .._message import Message, MessageType, unconditional_messages
from ..plugin import _plugin_lookup
from .. import _yaml, _signals


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
# Args:
#    scheduler (Scheduler): The scheduler
#    element (Element): The element to operate on
#    action_name (str): The queue action name
#
class Job():

    def __init__(self, scheduler, element, action_name):

        # Shared with child process
        self.scheduler = scheduler            # The scheduler
        self.queue = multiprocessing.Queue()  # A message passing queue
        self.process = None                   # The Process object
        self.watcher = None                   # Child process watcher
        self.action_name = action_name        # The action name for the Queue
        self.action = None                    # The action callable function
        self.complete = None                  # The complete callable function
        self.element = element                # The element we're processing
        self.listening = False                # Whether the parent is currently listening
        self.suspended = False                # Whether this job is currently suspended

        # Only relevant in parent process after spawning
        self.pid = None                       # The child's pid in the parent
        self.result = None                    # Return value of child action in the parent

        self.parent_start_listening()

    # spawn()
    #
    # Args:
    #    action (callable): The action function
    #    complete (callable): The function to call when complete
    #
    def spawn(self, action, complete):
        self.action = action
        self.complete = complete

        # Spawn the process
        self.process = Process(target=self.child_action,
                               args=[self.element, self.queue, self.action_name])

        # Here we want the following
        #
        #  A.) Child should inherit blocked SIGINT state, it's never handled there
        #  B.) Child should not inherit SIGTSTP handled state
        #
        with _signals.blocked([signal.SIGINT], discard=False):
            self.scheduler.loop.remove_signal_handler(signal.SIGTSTP)
            self.process.start()
            self.scheduler.loop.add_signal_handler(signal.SIGTSTP, self.scheduler.suspend_event)

        self.pid = self.process.pid

        # Wait for it to complete
        self.watcher = asyncio.get_child_watcher()
        self.watcher.add_child_handler(self.pid, self.child_complete, self.element)

    # shutdown()
    #
    # Should be called after the job completes
    #
    def shutdown(self):
        # Make sure we've read everything we need and then stop listening
        self.parent_process_queue()
        self.parent_stop_listening()

    # terminate()
    #
    # Forcefully terminates an ongoing job.
    #
    def terminate(self):

        # First resume the job if it's suspended
        self.resume(silent=True)

        self.message(self.element, MessageType.STATUS,
                     "{} terminating".format(self.action_name))

        # Make sure there is no garbage on the queue
        self.parent_stop_listening()

        # Terminate the process using multiprocessing API pathway
        self.process.terminate()

    # terminate_wait()
    #
    # Wait for terminated jobs to complete
    #
    # Args:
    #    timeout (float): Seconds to wait
    #
    # Returns:
    #    (bool): True if the process terminated cleanly, otherwise False
    def terminate_wait(self, timeout):

        # Join the child process after sending SIGTERM
        self.process.join(timeout)
        return (self.process.exitcode is not None)

    # kill()
    #
    # Forcefully kill the process
    #
    def kill(self):

        # Force kill
        self.message(self.element, MessageType.WARN,
                     "{} killing".format(self.action_name))
        os.kill(self.process.pid, signal.SIGKILL)

    # suspend()
    #
    # Suspend this job.
    #
    def suspend(self):
        if not self.suspended:
            self.message(self.element, MessageType.STATUS,
                         "{} suspending".format(self.action_name))

            # Use SIGTSTP so that child processes may handle and propagate
            # it to processes they spawn that become session leaders
            os.kill(self.process.pid, signal.SIGTSTP)

            # For some reason we receive exactly one suspend event for every
            # SIGTSTP we send to the child fork(), even though the child forks
            # are setsid(). We keep a count of these so we can ignore them
            # in our event loop suspend_event()
            self.scheduler.internal_stops += 1
            self.suspended = True

    # resume()
    #
    # Resume this suspended job.
    #
    def resume(self, silent=False):
        if self.suspended:
            if not silent:
                self.message(self.element, MessageType.STATUS,
                             "{} resuming".format(self.action_name))

            os.kill(self.process.pid, signal.SIGCONT)
            self.suspended = False

    # This can be used equally in the parent and child processes
    def message(self, plugin, message_type, message, **kwargs):
        args = dict(kwargs)
        args['scheduler'] = True
        self.scheduler.context._message(
            Message(plugin._get_unique_id(),
                    message_type,
                    message,
                    **args))

    #######################################################
    #                  Child Process                      #
    #######################################################
    def child_action(self, element, queue, action_name):

        # This avoids some SIGTSTP signals from grandchildren
        # getting propagated up to the master process
        os.setsid()

        # Assign the queue we passed across the process boundaries
        #
        # Set the global message handler in this child
        # process to forward messages to the parent process
        self.queue = queue
        self.scheduler.context._set_message_handler(self.child_message_handler)

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
            element._logging_enabled(action_name) as filename:

            self.message(element, MessageType.START, self.action_name,
                         logfile=filename)

            # Print the element's environment at the beginning of any element's log file.
            #
            # This should probably be omitted for non-build tasks but it's harmless here
            elt_env = _yaml.node_sanitize(element._Element__environment)
            env_dump = yaml.round_trip_dump(elt_env, default_flow_style=False, allow_unicode=True)
            self.message(element, MessageType.LOG,
                         "Build environment for element {}".format(element.name),
                         detail=env_dump, logfile=filename)

            try:
                result = self.action(element)
                if result is not None:
                    envelope = Envelope('result', result)
                    self.queue.put(envelope)

            except _BstError as e:
                elapsed = datetime.datetime.now() - starttime
                self.message(element, MessageType.FAIL, self.action_name,
                             elapsed=elapsed, detail=str(e),
                             logfile=filename, sandbox=e.sandbox)
                self.child_shutdown(1)

            except Exception as e:
                # If an unhandled (not normalized to _BstError) occurs, that's a bug,
                # send the traceback and formatted exception back to the frontend
                # and print it to the log file.
                #
                elapsed = datetime.datetime.now() - starttime
                detail = "An unhandled exception occured:\n\n{}".format(traceback.format_exc())
                self.message(element, MessageType.BUG, self.action_name,
                             elapsed=elapsed, detail=detail,
                             logfile=filename)
                self.child_shutdown(1)

            elapsed = datetime.datetime.now() - starttime
            self.message(element, MessageType.SUCCESS, self.action_name, elapsed=elapsed,
                         logfile=filename)

            self.child_shutdown(0)

    def child_complete(self, pid, returncode, element):
        self.complete(self, returncode, element)

    def child_shutdown(self, exit_code):
        self.queue.close()
        sys.exit(exit_code)

    def child_log(self, plugin, message, context):

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

    def child_message_handler(self, message, context):
        plugin = _plugin_lookup(message.unique_id)

        # Tag them on the way out the door...
        message.action_name = self.action_name
        message.task_id = self.element._get_unique_id()

        # Log first
        self.child_log(plugin, message, context)

        # Send to frontend if appropriate
        if (context._silent_messages() and
            message.message_type not in unconditional_messages):
            return

        if message.message_type == MessageType.LOG:
            return

        self.queue.put(Envelope('message', message))

    #######################################################
    #                 Parent Process                      #
    #######################################################
    def parent_process_envelope(self, envelope):
        if not self.listening:
            return

        if envelope.message_type == 'message':
            # Propagate received messages from children
            # back through the context.
            self.scheduler.context._message(envelope.message)
        elif envelope.message_type == 'result':
            assert(self.result is None)
            self.result = envelope.message
        else:
            raise Exception()

    def parent_process_queue(self):
        while not self.queue.empty():
            envelope = self.queue.get_nowait()
            self.parent_process_envelope(envelope)

    def parent_recv(self, *args):
        self.parent_process_queue()

    def parent_start_listening(self):
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
        if not self.listening:
            self.scheduler.loop.add_reader(
                self.queue._reader.fileno(), self.parent_recv)
            self.listening = True

    def parent_stop_listening(self):
        if self.listening:
            self.scheduler.loop.remove_reader(self.queue._reader.fileno())
            self.listening = False
