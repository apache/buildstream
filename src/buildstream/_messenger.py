#
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
#        Angelos Evripiotis <jevripiotis@bloomberg.net>

import os
import datetime
from contextlib import contextmanager

from . import _signals
from . import utils
from ._exceptions import BstError
from ._message import Message, MessageType
from .plugin import Plugin


class Messenger():

    def __init__(self):
        self._message_handler = None
        self._message_depth = []
        self._log_handle = None
        self._log_filename = None

    # set_message_handler()
    #
    # Sets the handler for any status messages propagated through
    # the context.
    #
    # The handler should have the signature:
    #
    #   def handler(
    #      message: _message.Message,  # The message to send.
    #      is_silenced: bool,          # Whether messages are currently being silenced.
    #   ) -> None
    #
    def set_message_handler(self, handler):
        self._message_handler = handler

    # _silent_messages():
    #
    # Returns:
    #    (bool): Whether messages are currently being silenced
    #
    def _silent_messages(self):
        return any(self._message_depth)

    # message():
    #
    # Proxies a message back to the caller, this is the central
    # point through which all messages pass.
    #
    # Args:
    #    message: A Message object
    #
    def message(self, message):

        # If we are recording messages, dump a copy into the open log file.
        self._record_message(message)

        # Send it off to the log handler (can be the frontend,
        # or it can be the child task which will propagate
        # to the frontend)
        assert self._message_handler

        self._message_handler(message, is_silenced=self._silent_messages())

    # silence()
    #
    # A context manager to silence messages, this behaves in
    # the same way as the `silent_nested` argument of the
    # timed_activity() context manager: especially
    # important messages will not be silenced.
    #
    @contextmanager
    def silence(self):
        self._push_message_depth(True)
        try:
            yield
        finally:
            self._pop_message_depth()

    # timed_activity()
    #
    # Context manager for performing timed activities and logging those
    #
    # Args:
    #    activity_name (str): The name of the activity
    #    context (Context): The invocation context object
    #    unique_id (int): Optionally, the unique id of the plugin related to the message
    #    detail (str): An optional detailed message, can be multiline output
    #    silent_nested (bool): If specified, nested messages will be silenced
    #
    @contextmanager
    def timed_activity(self, activity_name, *, unique_id=None, detail=None, silent_nested=False):

        starttime = datetime.datetime.now()
        stopped_time = None

        def stop_time():
            nonlocal stopped_time
            stopped_time = datetime.datetime.now()

        def resume_time():
            nonlocal stopped_time
            nonlocal starttime
            sleep_time = datetime.datetime.now() - stopped_time
            starttime += sleep_time

        with _signals.suspendable(stop_time, resume_time):
            try:
                # Push activity depth for status messages
                message = Message(unique_id, MessageType.START, activity_name, detail=detail)
                self.message(message)
                self._push_message_depth(silent_nested)
                yield

            except BstError:
                # Note the failure in status messages and reraise, the scheduler
                # expects an error when there is an error.
                elapsed = datetime.datetime.now() - starttime
                message = Message(unique_id, MessageType.FAIL, activity_name, elapsed=elapsed)
                self._pop_message_depth()
                self.message(message)
                raise

            elapsed = datetime.datetime.now() - starttime
            message = Message(unique_id, MessageType.SUCCESS, activity_name, elapsed=elapsed)
            self._pop_message_depth()
            self.message(message)

    # recorded_messages()
    #
    # Records all messages in a log file while the context manager
    # is active.
    #
    # In addition to automatically writing all messages to the
    # specified logging file, an open file handle for process stdout
    # and stderr will be available via the Messenger.get_log_handle() API,
    # and the full logfile path will be available via the
    # Messenger.get_log_filename() API.
    #
    # Args:
    #     filename (str): A logging directory relative filename,
    #                     the pid and .log extension will be automatically
    #                     appended
    #
    #     logdir (str)  : The path to the log file directory.
    #
    # Yields:
    #     (str): The fully qualified log filename
    #
    @contextmanager
    def recorded_messages(self, filename, logdir):

        # We dont allow recursing in this context manager, and
        # we also do not allow it in the main process.
        assert self._log_handle is None
        assert self._log_filename is None
        assert not utils._is_main_process()

        # Create the fully qualified logfile in the log directory,
        # appending the pid and .log extension at the end.
        self._log_filename = os.path.join(logdir,
                                          '{}.{}.log'.format(filename, os.getpid()))

        # Ensure the directory exists first
        directory = os.path.dirname(self._log_filename)
        os.makedirs(directory, exist_ok=True)

        with open(self._log_filename, 'a') as logfile:

            # Write one last line to the log and flush it to disk
            def flush_log():

                # If the process currently had something happening in the I/O stack
                # then trying to reenter the I/O stack will fire a runtime error.
                #
                # So just try to flush as well as we can at SIGTERM time
                try:
                    logfile.write('\n\nForcefully terminated\n')
                    logfile.flush()
                except RuntimeError:
                    os.fsync(logfile.fileno())

            self._log_handle = logfile
            with _signals.terminator(flush_log):
                yield self._log_filename

            self._log_handle = None
            self._log_filename = None

    # get_log_handle()
    #
    # Fetches the active log handle, this will return the active
    # log file handle when the Messenger.recorded_messages() context
    # manager is active
    #
    # Returns:
    #     (file): The active logging file handle, or None
    #
    def get_log_handle(self):
        return self._log_handle

    # get_log_filename()
    #
    # Fetches the active log filename, this will return the active
    # log filename when the Messenger.recorded_messages() context
    # manager is active
    #
    # Returns:
    #     (str): The active logging filename, or None
    #
    def get_log_filename(self):
        return self._log_filename

    # _record_message()
    #
    # Records the message if recording is enabled
    #
    # Args:
    #    message (Message): The message to record
    #
    def _record_message(self, message):

        if self._log_handle is None:
            return

        INDENT = "    "
        EMPTYTIME = "--:--:--"
        template = "[{timecode: <8}] {type: <7}"

        # If this message is associated with a plugin, print what
        # we know about the plugin.
        plugin_name = ""
        if message.unique_id:
            template += " {plugin}"
            plugin = Plugin._lookup(message.unique_id)
            plugin_name = plugin.name

        template += ": {message}"

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

        text = template.format(timecode=timecode,
                               plugin=plugin_name,
                               type=message.message_type.upper(),
                               message=message.message,
                               detail=detail)

        # Write to the open log file
        self._log_handle.write('{}\n'.format(text))
        self._log_handle.flush()

    # _push_message_depth() / _pop_message_depth()
    #
    # For status messages, send the depth of timed
    # activities inside a given task through the message
    #
    def _push_message_depth(self, silent_nested):
        self._message_depth.append(silent_nested)

    def _pop_message_depth(self):
        assert self._message_depth
        self._message_depth.pop()
