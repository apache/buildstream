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
import os
import signal
import sys
import threading
import traceback
from contextlib import contextmanager, ExitStack
from collections import deque
from typing import Callable, Deque


# Global per process state for handling of sigterm/sigtstp/sigcont,
# note that it is expected that this only ever be used by new processes
# the scheduler starts, not the main process.
#
terminator_stack: Deque[Callable] = deque()
suspendable_stack: Deque[Callable] = deque()

terminator_lock = threading.Lock()
suspendable_lock = threading.Lock()

# This event is used to block all the threads while we wait for user
# interaction. This is because we can't stop all the pythin threads but the
# one easily when waiting for user input. However, most performance intensive
# tasks will pass through a subprocess or a multiprocess.Process and all of
# those are guarded by the signal handling. Thus, by setting and unsetting this
# event in the scheduler, we can enable and disable the launching of processes
# and ensure we don't do anything resource intensive while being interrupted.
is_not_suspended = threading.Event()
is_not_suspended.set()


class TerminateException(BaseException):
    pass


# Per process SIGTERM handler
def terminator_handler(signal_, frame):
    exit_code = -1

    while terminator_stack:
        terminator_ = terminator_stack.pop()
        try:
            terminator_()
        except SystemExit as e:
            exit_code = e.code or 0
        except:  # noqa pylint: disable=bare-except
            # Ensure we print something if there's an exception raised when
            # processing the handlers. Note that the default exception
            # handler won't be called because we os._exit next, so we must
            # catch all possible exceptions with the unqualified 'except'
            # clause.
            traceback.print_exc(file=sys.stderr)
            print(
                "Error encountered in BuildStream while processing custom SIGTERM handler:",
                terminator_,
                file=sys.stderr,
            )

    # Use special exit here, terminate immediately, recommended
    # for precisely this situation where child processes are teminated.
    os._exit(exit_code)


# terminator()
#
# A context manager for interruptable tasks, this guarantees
# that while the code block is running, the supplied function
# will be called upon process termination.
#
# /!\ The callbacks passed must only contain code that does not acces thread
#     local variables. Those will run in the main thread.
#
# Note that after handlers are called, the termination will be handled by
# terminating immediately with os._exit(). This means that SystemExit will not
# be raised and 'finally' clauses will not be executed.
#
# Args:
#    terminate_func (callable): A function to call when aborting
#                               the nested code block.
#
@contextmanager
def terminator(terminate_func):
    global terminator_stack  # pylint: disable=global-statement,global-variable-not-assigned

    outermost = bool(not terminator_stack)

    assert threading.current_thread() == threading.main_thread() or not outermost

    with terminator_lock:
        terminator_stack.append(terminate_func)

    if outermost:
        original_handler = signal.signal(signal.SIGTERM, terminator_handler)

    try:
        yield
    except TerminateException:
        terminate_func()
        raise
    finally:
        if outermost:
            signal.signal(signal.SIGTERM, original_handler)

        with terminator_lock:
            terminator_stack.remove(terminate_func)


# Just a simple object for holding on to two callbacks
class Suspender:
    def __init__(self, suspend_callback, resume_callback):
        self.suspend = suspend_callback
        self.resume = resume_callback


# Per process SIGTSTP handler
def suspend_handler(sig, frame):
    is_not_suspended.clear()

    # Suspend callbacks from innermost frame first
    with suspendable_lock:
        for suspender in reversed(suspendable_stack):
            suspender.suspend()

        # Use SIGSTOP directly now on self, dont introduce more SIGTSTP
        #
        # Here the process sleeps until SIGCONT, which we simply
        # dont handle. We know we'll pickup execution right here
        # when we wake up.
        os.kill(os.getpid(), signal.SIGSTOP)

        # Resume callbacks from outermost frame inwards
        for suspender in suspendable_stack:
            suspender.resume()

    is_not_suspended.set()


# suspendable()
#
# A context manager for handling process suspending and resumeing
#
# Args:
#    suspend_callback (callable): A function to call as process suspend time.
#    resume_callback (callable): A function to call as process resume time.
#
# /!\ The callbacks passed must only contain code that does not acces thread
#     local variables. Those will run in the main thread.
#
# This must be used in code blocks which start processes that become
# their own session leader. In these cases, SIGSTOP and SIGCONT need
# to be propagated to the child process group.
#
# This context manager can also be used recursively, so multiple
# things can happen at suspend/resume time (such as tracking timers
# and ensuring durations do not count suspended time).
#
@contextmanager
def suspendable(suspend_callback, resume_callback):
    global suspendable_stack  # pylint: disable=global-statement,global-variable-not-assigned

    outermost = bool(not suspendable_stack)
    assert threading.current_thread() == threading.main_thread() or not outermost

    # If we are not in the main thread, ensure that we are not suspended
    # before running.
    # If we are in the main thread, never block on this, to ensure we
    # don't deadlock.
    if threading.current_thread() != threading.main_thread():
        is_not_suspended.wait()

    suspender = Suspender(suspend_callback, resume_callback)

    with suspendable_lock:
        suspendable_stack.append(suspender)

    if outermost:
        original_stop = signal.signal(signal.SIGTSTP, suspend_handler)

    try:
        yield
    finally:
        if outermost:
            signal.signal(signal.SIGTSTP, original_stop)

        with suspendable_lock:
            suspendable_stack.remove(suspender)


# blocked()
#
# A context manager for running a code block with blocked signals
#
# Args:
#    signals (list): A list of unix signals to block
#    ignore (bool): Whether to ignore entirely the signals which were
#                   received and pending while the process had blocked them
#
@contextmanager
def blocked(signal_list, ignore=True):

    with ExitStack() as stack:

        # Optionally add the ignored() context manager to this context
        if ignore:
            stack.enter_context(ignored(signal_list))

        # Set and save the sigprocmask
        blocked_signals = signal.pthread_sigmask(signal.SIG_BLOCK, signal_list)

        try:
            yield
        finally:
            # If we have discarded the signals completely, this line will cause
            # the discard_handler() to trigger for each signal in the list
            signal.pthread_sigmask(signal.SIG_SETMASK, blocked_signals)


# ignored()
#
# A context manager for running a code block with ignored signals
#
# Args:
#    signals (list): A list of unix signals to ignore
#
@contextmanager
def ignored(signal_list):

    orig_handlers = {}
    for sig in signal_list:
        orig_handlers[sig] = signal.signal(sig, signal.SIG_IGN)

    try:
        yield
    finally:
        for sig in signal_list:
            signal.signal(sig, orig_handlers[sig])
