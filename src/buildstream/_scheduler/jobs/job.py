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
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
#        Jürg Billeter <juerg.billeter@codethink.co.uk>
#        Tristan Maat <tristan.maat@codethink.co.uk>

# System imports
import asyncio
import datetime
import itertools
import threading
import traceback
from contextlib import ExitStack

# BuildStream toplevel imports
from ... import utils
from ..._utils import terminate_thread
from ..._exceptions import ImplError, BstError, set_last_task_error, SkipJob
from ..._message import Message, MessageType
from ...types import FastEnum
from ..._signals import TerminateException


# Return code values of child tasks of a job
#
class _ReturnCode(FastEnum):
    OK = 0
    FAIL = 1
    PERM_FAIL = 2
    SKIPPED = 3
    TERMINATED = 4


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


# Job()
#
# The Job object represents a task that will run in parallel to the main
# thread. It has some methods that are not implemented - they are meant for
# you to implement in a subclass.
#
# Args:
#    scheduler (Scheduler): The scheduler
#    action_name (str): The queue action name
#    logfile (str): A template string that points to the logfile
#                   that should be used - should contain {pid}.
#    max_retries (int): The maximum number of retries
#
class Job:
    # Unique id generator for jobs
    #
    # This is used to identify tasks in the `State` class
    _id_generator = itertools.count(1)

    def __init__(self, scheduler, action_name, logfile, *, max_retries=0):

        #
        # Public members
        #
        self.id = "{}-{}".format(action_name, next(Job._id_generator))
        self.name = None  # The name of the job, set by the job's subclass
        self.action_name = action_name  # The action name for the Queue

        #
        # Private members
        #
        self._scheduler = scheduler  # The scheduler
        self._messenger = self._scheduler.context.messenger
        self._suspended = False  # Whether this job is currently suspended
        self._max_retries = max_retries  # Maximum number of automatic retries
        self._result = None  # Return value of child action in the parent
        self._tries = 0  # Try count, for retryable jobs
        self._terminated = False  # Whether this job has been explicitly terminated

        self._logfile = logfile
        self._message_element_name = None  # The task-wide element name
        self._message_element_key = None  # The task-wide element cache key
        self._element = None  # The Element() passed to the Job() constructor, if applicable

        self._task = None  # The task that is run

        self._thread_id = None  # Thread in which the child executes its action
        self._should_terminate = False
        self._terminate_lock = threading.Lock()

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

        assert not self._terminated, "Attempted to start a job which was already terminated"

        self._tries += 1

        loop = asyncio.get_event_loop()

        async def execute():
            ret_code, self._result = await loop.run_in_executor(None, self.child_action)
            await self._parent_child_completed(ret_code)

        self._task = loop.create_task(execute())

    # terminate()
    #
    # Politely request that an ongoing job terminate soon.
    #
    # This will raise an exception in the child to ask it to exit.
    #
    def terminate(self):
        self.message(MessageType.STATUS, "{} terminating".format(self.action_name))

        if self._task:
            assert utils._is_in_main_thread(), "Terminating the job's thread should only be done from the scheduler"

            if self._should_terminate:
                return

            with self._terminate_lock:
                self._should_terminate = True
                if self._thread_id is None:
                    return

            terminate_thread(self._thread_id)
        self._terminated = True

    # get_terminated()
    #
    # Check if a job has been terminated.
    #
    # Returns:
    #     (bool): True in the main thread if Job.terminate() was called.
    #
    def get_terminated(self):
        return self._terminated

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
    #     element_key (_DisplayKey): The element_key tuple to be supplied to the Message() constructor
    #
    def set_message_element_key(self, element_key):
        self._message_element_key = element_key

    # message():
    #
    # Logs a message, this will be logged in the task's logfile and
    # conditionally also be sent to the frontend.
    #
    # Args:
    #    message_type (MessageType): The type of message to send
    #    message (str): The message
    #    kwargs: Remaining Message() constructor arguments, note that you can
    #            override 'element_name' and 'element_key' this way.
    #
    def message(self, message_type, message, **kwargs):
        kwargs["scheduler"] = True
        message = Message(
            message_type,
            message,
            element_name=self._message_element_name,
            element_key=self._message_element_key,
            **kwargs
        )
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

    # child_process()
    #
    # This will be executed in a thread, and is intended to perform the job's task.
    #
    # Returns:
    #    (any): A simple object (must be pickle-able, i.e. strings, lists,
    #           dicts, numbers, but not Element instances). It is returned to
    #           the parent Job running in the main process. This is taken as
    #           the result of the Job.
    #
    def child_process(self):
        raise ImplError("Job '{kind}' does not implement child_process()".format(kind=type(self).__name__))

    # parent_complete()
    #
    # This will be executed in the main thread after the job finishes, and is
    # expected to pass the result to the main thread.
    #
    # Args:
    #    status (JobStatus): The job exit status
    #    result (any): The result returned by child_process().
    #
    def parent_complete(self, status, result):
        raise ImplError("Job '{kind}' does not implement parent_complete()".format(kind=type(self).__name__))

    #######################################################
    #                  Local Private Methods              #
    #######################################################

    # _parent_child_completed()
    #
    # Called in the main process courtesy of asyncio's ChildWatcher.add_child_handler()
    #
    # Args:
    #    returncode (int): The return code of the child process
    #
    async def _parent_child_completed(self, returncode):
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
                self.message(MessageType.INFO, "Job terminated")
            else:
                self.message(MessageType.ERROR, "Job was terminated unexpectedly")

            status = JobStatus.FAIL
        else:
            status = JobStatus.FAIL

        self.parent_complete(status, self._result)
        self._scheduler.job_completed(self, status)
        self._task = None

    # child_action()
    #
    # Perform the action in the child process, this calls the action_cb.
    #
    def child_action(self):
        # Set the global message handler in this child
        # process to forward messages to the parent process
        self._messenger.setup_new_action_context(
            self.action_name, self._message_element_name, self._message_element_key
        )

        with ExitStack() as stack:
            # Time, log and and run the action function
            #
            timeinfo = stack.enter_context(self._messenger.timed_suspendable())

            try:
                filename = (
                    stack.enter_context(
                        self._messenger.recorded_messages(self._logfile, self._scheduler.context.logdir)
                    )
                    if self._logfile
                    else None
                )
            except Exception as e:  # pylint: disable=broad-except
                elapsed = datetime.datetime.now() - timeinfo.start_time
                self.message(
                    MessageType.ERROR,
                    "Error opening log file: {}".format(e),
                    elapsed=elapsed,
                    detail=traceback.format_exc(),
                )
                self._thread_id = None
                return _ReturnCode.PERM_FAIL, None

            try:
                self.message(MessageType.START, self.action_name, logfile=filename)

                with self._terminate_lock:
                    self._thread_id = threading.current_thread().ident
                    if self._should_terminate:
                        return _ReturnCode.TERMINATED, None

                try:
                    # Try the task action
                    result = self.child_process()  # pylint: disable=assignment-from-no-return
                except SkipJob as e:
                    elapsed = datetime.datetime.now() - timeinfo.start_time
                    self.message(MessageType.SKIPPED, str(e), elapsed=elapsed, logfile=filename)

                    # Alert parent of skip by return code
                    return _ReturnCode.SKIPPED, None
                except BstError as e:
                    elapsed = datetime.datetime.now() - timeinfo.start_time
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
                            MessageType.FAIL,
                            str(e),
                            elapsed=elapsed,
                            detail=e.detail,
                            logfile=filename,
                            sandbox=e.sandbox,
                        )

                    # Report the exception to the parent (for internal testing purposes)
                    set_last_task_error(e.domain, e.reason)

                    # Set return code based on whether or not the error was temporary.
                    #
                    return _ReturnCode.FAIL if retry_flag else _ReturnCode.PERM_FAIL, None
                except Exception:  # pylint: disable=broad-except

                    # If an unhandled (not normalized to BstError) occurs, that's a bug,
                    # send the traceback and formatted exception back to the frontend
                    # and print it to the log file.
                    #
                    elapsed = datetime.datetime.now() - timeinfo.start_time
                    detail = "An unhandled exception occured:\n\n{}".format(traceback.format_exc())

                    self.message(MessageType.BUG, self.action_name, elapsed=elapsed, detail=detail, logfile=filename)
                    # Unhandled exceptions should permenantly fail
                    return _ReturnCode.PERM_FAIL, None

                else:
                    # No exception occurred in the action
                    elapsed = datetime.datetime.now() - timeinfo.start_time
                    self.message(MessageType.SUCCESS, self.action_name, elapsed=elapsed, logfile=filename)

                    # Shutdown needs to stay outside of the above context manager,
                    # make sure we dont try to handle SIGTERM while the process
                    # is already busy in sys.exit()
                    return _ReturnCode.OK, result
                finally:
                    self._thread_id = None
            except TerminateException:
                self._thread_id = None
                return _ReturnCode.TERMINATED, None
