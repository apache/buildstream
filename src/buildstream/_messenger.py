#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
#  Authors:
#        Angelos Evripiotis <jevripiotis@bloomberg.net>

import os
import datetime
import threading
from contextlib import contextmanager
from typing import Optional, Callable, Iterator, TextIO

from .types import _DisplayKey
from . import _signals
from ._exceptions import BstError
from ._message import Message, MessageType, unconditional_messages
from ._state import State, Task
from ._version import get_versions


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


# _JobInfo
#
# Information about a job, used as a part of thread local storage
# in order to fill in some Message parameters automatically.
#
class _JobInfo:
    def __init__(self, action_name: str, element_name: str, element_key: _DisplayKey) -> None:
        self.action_name = action_name
        self.element_name = element_name
        self.element_key = element_key


# _MessengerLocal
#
# Thread local storage for the messenger
#
class _MessengerLocal(threading.local):
    def __init__(self) -> None:
        super().__init__()

        # The open file handle for this task
        self.log_handle: Optional[TextIO] = None

        # The filename for this task
        self.log_filename: Optional[str] = None

        # Level of silent messages depth in this task
        self.silence_scope_depth: int = 0

        # Job
        self.job: Optional[_JobInfo] = None


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

        # The callback to call when propagating messages
        #
        # FIXME: The message handler is currently not strongly typed,
        #        as it uses a kwarg, we cannot declare it with Callable.
        #        We can use `Protocol` to strongly type this with python >= 3.8
        self._message_handler = None

        # Save the bst version to record in log files
        #
        self._bst_version = get_versions()["version"]

    # setup_new_action_context()
    #
    # Setup the thread local context for a new task, some message
    # components are filled in automatically based on the action context.
    #
    # Args:
    #    action_name: The action name
    #    element_name: The element name
    #    element_key: The element's DisplayKey
    #
    def setup_new_action_context(self, action_name: str, element_name: str, element_key: _DisplayKey) -> None:
        self._locals.silence_scope_depth = 0
        self._locals.job = _JobInfo(action_name, element_name, element_key)

    # set_message_handler()
    #
    # Sets the handler for any status messages propagated through
    # the messenger.
    #
    def set_message_handler(self, handler) -> None:
        self._message_handler = handler

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

        # Always add the log filename automatically
        message.logfile = self._locals.log_filename

        is_silenced = self._silent_messages()
        job = self._locals.job

        if job is not None:
            # Automatically add message information from the job context
            message.action_name = job.action_name
            message.task_element_name = job.element_name
            message.task_element_key = job.element_key

            # Don't forward LOG messages from jobs
            if message.message_type == MessageType.LOG:
                return

            # Don't forward JOB messages if they are currently silent
            if is_silenced and (message.message_type not in unconditional_messages):
                return

        # Send it off to the log handler (can be the frontend,
        # or it can be the child task which will propagate
        # to the frontend)
        assert self._message_handler
        self._message_handler(message, is_silenced=is_silenced)

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

        # Ensure the directory exists first
        directory = os.path.dirname(self._locals.log_filename)
        os.makedirs(directory, exist_ok=True)

        with open(self._locals.log_filename, "a", encoding="utf-8") as logfile:

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

            # Unconditionally record date and buildstream version at the beginning of any log file
            #
            starttime = datetime.datetime.now()
            logfile.write(
                "BuildStream {} - {}\n".format(self._bst_version, starttime.strftime("%A, %d-%m-%Y at %H:%M:%S"))
            )

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
            assert message.elapsed is not None
            hours, remainder = divmod(int(message.elapsed.total_seconds()), 60**2)
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
