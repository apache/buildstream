#!/usr/bin/env python3
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
from contextlib import contextmanager
from collections import deque


# Global per process state for handling of sigterm/sigtstp/sigcont,
# note that it is expected that this only ever be used by processes
# the scheduler forks off, not the main process
terminator_stack = deque()
suspendable_stack = deque()


class Suspender():
    def __init__(self, suspend_callback, resume_callback):
        self.suspend = suspend_callback
        self.resume = resume_callback


# Per process SIGTERM handler
def terminator_handler(signal, frame):
    while terminator_stack:
        terminator = terminator_stack.pop()
        terminator()

    # Use special exit here, terminate immediately, recommended
    # for precisely this situation where child forks are teminated.
    os._exit(-1)


# Per process SIGTSTP handler
def suspend_handler(sig, frame):

    # Suspend callbacks from innermost frame first
    for suspender in reversed(suspendable_stack):
        suspender.suspend()

    # Use SIGSTOP directly now, dont introduce more SIGTSTP
    os.kill(os.getpid(), signal.SIGSTOP)


# Per process SIGCONT handler
def resume_handler(sig, frame):

    # Resume callbacks from outermost frame inwards
    for suspender in suspendable_stack:
        suspender.resume()


# terminator()
#
# A context manager for interruptable tasks, this guarantees
# that while the code block is running, the supplied function
# will be called upon process termination.
#
# Args:
#    terminate_func (callable): A function to call when aborting
#                               the nested code block.
#
@contextmanager
def terminator(terminate_func):
    global terminator_stack

    outermost = False if terminator_stack else True

    terminator_stack.append(terminate_func)
    if outermost:
        original_handler = signal.signal(signal.SIGTERM, terminator_handler)

    yield

    if outermost:
        signal.signal(signal.SIGTERM, original_handler)
    terminator_stack.pop()


# suspendable()
#
# A context manager for a code block which spawns a process
# that becomes its own session leader.
#
# In these cases, SIGSTOP and SIGCONT need to be propagated to
# the child tasks, this is not expected to be used recursively,
# as the codeblock is expected to just spawn a processes.
#
@contextmanager
def suspendable(suspend_callback, resume_callback):
    global suspendable_stack

    outermost = False if suspendable_stack else True
    suspender = Suspender(suspend_callback, resume_callback)
    suspendable_stack.append(suspender)

    if outermost:
        original_cont = signal.signal(signal.SIGCONT, resume_handler)
        original_stop = signal.signal(signal.SIGTSTP, suspend_handler)

    yield

    if outermost:
        signal.signal(signal.SIGTSTP, original_stop)
        signal.signal(signal.SIGCONT, original_cont)

    suspendable_stack.pop()
