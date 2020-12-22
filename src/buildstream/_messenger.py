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
import threading
from contextlib import contextmanager
from typing import Optional, Callable, Iterator, TextIO

from . import _signals
from ._exceptions import BstError
from ._message import Message, MessageType
from ._state import State, Task


_RENDER_INTERVAL: datetime.timedelta = datetime.timedelta(seconds=1)


# Time in seconds for which we decide that we want to display subtask information
_DISPLAY_LIMIT: datetime.timedelta = datetime.timedelta(seconds=3)
# If we're in the test suite, we need to ensure that we don't set a limit
if "BST_TEST_SUITE" in os.environ:
    _DISPLAY_LIMIT = datetime.timedelta(seconds=0)


# TimeData class to contain times in an object that can be passed around
# and updated from different places
class _TimeData:
    __slots__ = ["start_time"]

    def __init__(self, start_time: datetime.datetime) -> None:
        self.start_time: datetime.datetime = start_time


# _MessengerLocal
#
# Thread local storage for the messenger
#
class _MessengerLocal(threading.local):
    def __init__(self) -> None:
        super().__init__()

        # The callback to call when propagating messages
        #
        # FIXME: The message handler is currently not strongly typed,
        #        as it uses a kwarg, we cannot declare it with Callable.
        #        We can use `Protocol` to strongly type this with python >= 3.8
        self.message_handler = None

        # The open file handle for this task
        self.log_handle: Optional[TextIO] = None

        # The filename for this task
        self.log_filename: Optional[str] = None

        # Level of silent messages depth in this task
        self.silence_scope_depth: int = 0


# Messenger()
#
# The messenger object.
#
# This is used to propagate messages either from the main context or
# from task contexts in such a way that messages are propagated to
# the frontend and also optionally recorded to a task log file when
# the message is issued from a task context.
#
class Messenger:
    def __init__(self) -> None:
        self._state: Optional[State] = None  # The State object

        #
        # State related to simple tasks, these drive the status bar
        # when ongoing activities occur outside of an active scheduler
        #
        self._active_simple_tasks: int = 0  # Number of active simple tasks
        self._next_render: Optional[datetime.datetime] = None  # The time of the next render
        self._render_status_cb: Optional[Callable[[], None]] = None  # The render callback

        # Thread local storage
        self._locals: _MessengerLocal = _MessengerLocal()

    # set_message_handler()
    #
    # Sets the handler for any status messages propagated through
    # the messenger.
    #
    def set_message_handler(self, handler) -> None:
        self._locals.message_handler = handler

    # set_state()
    #
    # Sets the State object within the Messenger
    #
    # Args:
    #    state: The state to set
    #
    def set_state(self, state: State) -> None:
        self._state = state

    # set_render_status_cb()
    #
    # Sets the callback to use to render status
    #
    # Args:
    #    callback: The Callback to be notified
    #
    def set_render_status_cb(self, callback: Callable[[], None]) -> None:
        self._render_status_cb = callback

    # message():
    #
    # Proxies a message back to the caller, this is the central
    # point through which all messages pass.
    #
    # Args:
    #    message: A Message object
    #
    def message(self, message: Message) -> None:
        # If we are recording messages, dump a copy into the open log file.
        self._record_message(message)

        # Send it off to the log handler (can be the frontend,
        # or it can be the child task which will propagate
        # to the frontend)
        assert self._locals.message_handler

        self._locals.message_handler(message, is_silenced=self._silent_messages())

    # status():
    #
    # A core facing convenience method for issuing STATUS messages
    #
    # Args:
    #    brief: The brief status message
    #    detail: An optional detailed message
    #    kwargs: Additional Message constructor keyword arguments
    #
    def status(self, brief: str, *, detail: Optional[str] = None, **kwargs) -> None:
        message = Message(MessageType.STATUS, brief, detail=detail, **kwargs)
        self.message(message)

    # info():
    #
    # A core facing convenience method for issuing INFO messages
    #
    # Args:
    #    brief: The brief info message
    #    detail: An optional detailed message
    #    kwargs: Additional Message constructor keyword arguments
    #
    def info(self, brief: str, *, detail: Optional[str] = None, **kwargs) -> None:
        message = Message(MessageType.INFO, brief, detail=detail, **kwargs)
        self.message(message)

    # warn():
    #
    # A core facing convenience method for issuing WARN messages
    #
    # Args:
    #    brief: The brief warning message
    #    detail: An optional detailed message
    #    kwargs: Additional Message constructor keyword arguments
    #
    def warn(self, brief: str, *, detail: Optional[str] = None, **kwargs) -> None:
        message = Message(MessageType.WARN, brief, detail=detail, **kwargs)
        self.message(message)

    # error():
    #
    # A core facing convenience method for issuing ERROR messages
    #
    # Args:
    #    brief: The brief error message
    #    detail: An optional detailed message
    #    kwargs: Additional Message constructor keyword arguments
    #
    def error(self, brief: str, *, detail: Optional[str] = None, **kwargs) -> None:
        message = Message(MessageType.ERROR, brief, detail=detail, **kwargs)
        self.message(message)

    # bug():
    #
    # A core facing convenience method for issuing BUG messages
    #
    # Args:
    #    brief: The brief bug message
    #    detail: An optional detailed message
    #    kwargs: Additional Message constructor keyword arguments
    #
    def bug(self, brief: str, *, detail: Optional[str] = None, **kwargs) -> None:
        message = Message(MessageType.BUG, brief, detail=detail, **kwargs)
        self.message(message)

    # silence()
    #
    # A context manager to silence messages, this behaves in
    # the same way as the `silent_nested` argument of the
    # timed_activity() context manager: all but
    # _message.unconditional_messages will be silenced.
    #
    # Args:
    #    actually_silence: Whether to actually do the silencing, if
    #                      False then this context manager does not
    #                      affect anything.
    #
    @contextmanager
    def silence(self, *, actually_silence: bool = True) -> Iterator[None]:
        if not actually_silence:
            yield None
            return

        self._locals.silence_scope_depth += 1
        try:
            yield None
        finally:
            assert self._locals.silence_scope_depth > 0
            self._locals.silence_scope_depth -= 1

    # timed_activity()
    #
    # Context manager for performing timed activities and logging those
    #
    # Args:
    #    activity_name: The name of the activity
    #    detail: An optional detailed message, can be multiline output
    #    silent_nested: If True, all nested messages are silenced except for unconditionaly ones
    #    kwargs: Remaining Message() constructor keyword arguments.
    #
    @contextmanager
    def timed_activity(
        self, activity_name: str, *, detail: str = None, silent_nested: bool = False, **kwargs
    ) -> Iterator[None]:
        with self.timed_suspendable() as timedata:
            try:
                # Push activity depth for status messages
                message = Message(MessageType.START, activity_name, detail=detail, **kwargs)
                self.message(message)
                with self.silence(actually_silence=silent_nested):
                    yield None

            except BstError:
                # Note the failure in status messages and reraise, the scheduler
                # expects an error when there is an error.
                elapsed = datetime.datetime.now() - timedata.start_time
                message = Message(MessageType.FAIL, activity_name, elapsed=elapsed, **kwargs)
                self.message(message)
                raise

            elapsed = datetime.datetime.now() - timedata.start_time
            message = Message(MessageType.SUCCESS, activity_name, elapsed=elapsed, **kwargs)
            self.message(message)

    # simple_task()
    #
    # Context manager for creating a task to report progress to.
    #
    # Args:
    #    activity_name: The name of the activity
    #    task_name: Optionally, the task name for the frontend during this task
    #    detail: An optional detailed message, can be multiline output
    #    silent_nested: If True, all nested messages are silenced except for unconditionaly ones
    #    kwargs: Remaining Message() constructor keyword arguments.
    #
    # Yields:
    #    Task: A Task object that represents this activity, principally used to report progress
    #
    @contextmanager
    def simple_task(
        self, activity_name: str, *, task_name: str = None, detail: str = None, silent_nested: bool = False, **kwargs
    ) -> Iterator[Optional[Task]]:
        # Bypass use of State when none exists (e.g. tests)
        if not self._state:
            with self.timed_activity(activity_name, detail=detail, silent_nested=silent_nested, **kwargs):
                yield None
            return

        if not task_name:
            task_name = activity_name

        with self.timed_suspendable() as timedata:
            try:
                message = Message(MessageType.START, activity_name, detail=detail, **kwargs)
                self.message(message)

                task = self._state.add_task(task_name, activity_name, task_name)
                task.set_task_changed_callback(self._render_status)
                self._active_simple_tasks += 1
                if not self._next_render:
                    self._next_render = datetime.datetime.now() + _RENDER_INTERVAL

                with self.silence(actually_silence=silent_nested):
                    yield task

            except BstError:
                elapsed = datetime.datetime.now() - timedata.start_time
                message = Message(MessageType.FAIL, activity_name, elapsed=elapsed, **kwargs)
                self.message(message)
                raise
            finally:
                self._state.remove_task(task_name)
                self._active_simple_tasks -= 1
                if self._active_simple_tasks == 0:
                    self._next_render = None

            elapsed = datetime.datetime.now() - timedata.start_time
            detail = None

            if task.current_progress is not None and elapsed > _DISPLAY_LIMIT:
                if task.maximum_progress is not None:
                    detail = "{} of {} subtasks processed".format(task.current_progress, task.maximum_progress)
                else:
                    detail = "{} subtasks processed".format(task.current_progress)
            message = Message(MessageType.SUCCESS, activity_name, elapsed=elapsed, detail=detail, **kwargs)
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
    #    filename: A logging directory relative filename,
    #              the pid and .log extension will be automatically
    #              appended
    #
    #    logdir: The path to the log file directory.
    #
    # Yields:
    #    The fully qualified log filename
    #
    @contextmanager
    def recorded_messages(self, filename: str, logdir: str) -> Iterator[str]:
        # We dont allow recursing in this context manager, and
        # we also do not allow it in the main process.
        assert not hasattr(self._locals, "log_handle") or self._locals.log_handle is None
        assert not hasattr(self._locals, "log_filename") or self._locals.log_filename is None

        # Create the fully qualified logfile in the log directory,
        # appending the pid and .log extension at the end.
        self._locals.log_filename = os.path.join(logdir, "{}.{}.log".format(filename, os.getpid()))
        self._locals.silence_scope_depth = 0

        # Ensure the directory exists first
        directory = os.path.dirname(self._locals.log_filename)
        os.makedirs(directory, exist_ok=True)

        with open(self._locals.log_filename, "a") as logfile:

            # Write one last line to the log and flush it to disk
            def flush_log():

                # If the process currently had something happening in the I/O stack
                # then trying to reenter the I/O stack will fire a runtime error.
                #
                # So just try to flush as well as we can at SIGTERM time
                try:
                    logfile.write("\n\nForcefully terminated\n")
                    logfile.flush()
                except RuntimeError:
                    os.fsync(logfile.fileno())

            self._locals.log_handle = logfile
            with _signals.terminator(flush_log):
                yield self._locals.log_filename

            self._locals.log_handle = None
            self._locals.log_filename = None

    # get_log_handle()
    #
    # Fetches the active log handle, this will return the active
    # log file handle when the Messenger.recorded_messages() context
    # manager is active
    #
    # Returns:
    #    The active logging file handle, or None
    #
    def get_log_handle(self) -> Optional[TextIO]:
        return self._locals.log_handle

    # get_log_filename()
    #
    # Fetches the active log filename, this will return the active
    # log filename when the Messenger.recorded_messages() context
    # manager is active
    #
    # Returns:
    #    The active logging filename, or None
    #
    def get_log_filename(self) -> Optional[str]:
        return self._locals.log_filename

    # timed_suspendable()
    #
    # A contextmanager that allows an activity to be suspended and can
    # adjust for clock drift caused by suspending
    #
    # Yields:
    #    An object that contains the time the activity started
    #
    @contextmanager
    def timed_suspendable(self) -> Iterator[_TimeData]:
        # Note: timedata needs to be in a namedtuple so that values can be
        # yielded that will change
        timedata = _TimeData(start_time=datetime.datetime.now())
        stopped_time = None

        def stop_time():
            nonlocal stopped_time
            stopped_time = datetime.datetime.now()

        def resume_time():
            sleep_time = datetime.datetime.now() - stopped_time
            timedata.start_time += sleep_time

        with _signals.suspendable(stop_time, resume_time):
            yield timedata

    # _silent_messages():
    #
    # Returns:
    #    (bool): Whether messages are currently being silenced
    #
    def _silent_messages(self) -> bool:
        return self._locals.silence_scope_depth > 0

    # _record_message()
    #
    # Records the message if recording is enabled
    #
    # Args:
    #    message: The message to record
    #
    def _record_message(self, message: Message) -> None:

        if self._locals.log_handle is None:
            return

        INDENT = "    "
        EMPTYTIME = "--:--:--"
        template = "[{timecode: <8}] {type: <7}"

        # If this message is associated with an element or source plugin, print the
        # full element name and key for the instance.
        element_key = ""
        if message.element_key:
            template += " [{element_key}]"
            element_key = message.element_key.brief

        element_name = ""
        if message.element_name:
            template += " {element_name}"
            element_name = message.element_name

        template += ": {message}"

        detail = ""
        if message.detail is not None:
            template += "\n\n{detail}"
            detail = message.detail.rstrip("\n")
            detail = INDENT + INDENT.join(detail.splitlines(True))

        timecode = EMPTYTIME
        if message.message_type in (MessageType.SUCCESS, MessageType.FAIL):
            hours, remainder = divmod(int(message.elapsed.total_seconds()), 60 ** 2)
            minutes, seconds = divmod(remainder, 60)
            timecode = "{0:02d}:{1:02d}:{2:02d}".format(hours, minutes, seconds)

        text = template.format(
            timecode=timecode,
            element_key=element_key,
            element_name=element_name,
            type=message.message_type.upper(),
            message=message.message,
            detail=detail,
        )

        # Write to the open log file
        self._locals.log_handle.write("{}\n".format(text))
        self._locals.log_handle.flush()

    # _render_status()
    #
    # Calls the render status callback set in the messenger, but only if a
    # second has passed since it last rendered.
    #
    def _render_status(self) -> None:
        assert self._next_render

        # self._render_status_cb()
        now = datetime.datetime.now()
        if self._render_status_cb and now >= self._next_render:
            self._render_status_cb()
            self._next_render = now + _RENDER_INTERVAL
