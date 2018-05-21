#
#  Copyright (C) 2017 Codethink Limited
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
import os
import signal
import sys
import threading
import traceback
from contextlib import contextmanager, ExitStack
from collections import deque


# Global per process state for handling of sigterm/sigtstp/sigcont,
# note that it is expected that this only ever be used by processes
# the scheduler forks off, not the main process
terminator_stack = deque()
suspendable_stack = deque()


# Per process SIGTERM handler
def terminator_handler(signal_, frame):
    while terminator_stack:
        terminator_ = terminator_stack.pop()
        try:
            terminator_()
        except:                                                 # pylint: disable=bare-except
            # Ensure we print something if there's an exception raised when
            # processing the handlers. Note that the default exception
            # handler won't be called because we os._exit next, so we must
            # catch all possible exceptions with the unqualified 'except'
            # clause.
            traceback.print_exc(file=sys.stderr)
            print('Error encountered in BuildStream while processing custom SIGTERM handler:',
                  terminator_,
                  file=sys.stderr)

    # Use special exit here, terminate immediately, recommended
    # for precisely this situation where child forks are teminated.
    os._exit(-1)


# terminator()
#
# A context manager for interruptable tasks, this guarantees
# that while the code block is running, the supplied function
# will be called upon process termination.
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
    global terminator_stack                   # pylint: disable=global-statement

    # Signal handling only works in the main thread
    if threading.current_thread() != threading.main_thread():
        yield
        return

    outermost = False if terminator_stack else True

    terminator_stack.append(terminate_func)
    if outermost:
        original_handler = signal.signal(signal.SIGTERM, terminator_handler)

    try:
        yield
    finally:
        if outermost:
            signal.signal(signal.SIGTERM, original_handler)
        terminator_stack.pop()


# Just a simple object for holding on to two callbacks
class Suspender():
    def __init__(self, suspend_callback, resume_callback):
        self.suspend = suspend_callback
        self.resume = resume_callback


# Per process SIGTSTP handler
def suspend_handler(sig, frame):

    # Suspend callbacks from innermost frame first
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


# suspendable()
#
# A context manager for handling process suspending and resumeing
#
# Args:
#    suspend_callback (callable): A function to call as process suspend time.
#    resume_callback (callable): A function to call as process resume time.
#
# This must be used in code blocks which spawn processes that become
# their own session leader. In these cases, SIGSTOP and SIGCONT need
# to be propagated to the child process group.
#
# This context manager can also be used recursively, so multiple
# things can happen at suspend/resume time (such as tracking timers
# and ensuring durations do not count suspended time).
#
@contextmanager
def suspendable(suspend_callback, resume_callback):
    global suspendable_stack                  # pylint: disable=global-statement

    outermost = False if suspendable_stack else True
    suspender = Suspender(suspend_callback, resume_callback)
    suspendable_stack.append(suspender)

    if outermost:
        original_stop = signal.signal(signal.SIGTSTP, suspend_handler)

    try:
        yield
    finally:
        if outermost:
            signal.signal(signal.SIGTSTP, original_stop)

        suspendable_stack.pop()


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
