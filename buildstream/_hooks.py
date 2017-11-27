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
#        Tristan Maat <tristan.maat@codethink.co.uk>

import shlex
import itertools
import subprocess
import multiprocessing

import psutil

from . import _signals
from .utils import _kill_process_tree
from ._message import Message, MessageType


# Manages and executes hooks.
#
class Hooks():
    def __init__(self, context):
        self.context = context
        self.running = {}
        self._hooks = {}
        self.pool = None

    # Set a hook for a certain cause
    #
    # Args:
    #     cause (str): The cause to trigger the hook.
    #     text (commands): The commands to execute.
    #     project (str): The project name to execute on.
    #     element (str): The element name to execute on.
    #
    def set_hook(self, cause, commands, project='', element=''):
        if element == '':
            element = None

        if project == '':
            project = None

        self._hooks[cause] = Hook(cause, commands, project, element)

    # Run all hooks for the given cause, element and project, passing
    # 'text' to the stdin of their commands.
    #
    # Args:
    #     cause (str): The cause of the hooks to execute.
    #     text (str): text to pass on to the hooks for context.
    #     project (str): The project name.
    #     element (str): The element name.
    #
    def run_hook(self, cause, text, project=None, element=None):
        # Find the correct hook to run, ensuring that it has the
        # correct project and element.
        hook = self._hooks.get(cause, None)
        if hook is None:
            return
        if not (hook.project is None or hook.project == project):
            return
        if not (hook.element is None or hook.element == element):
            return

        # Execute all commands in a multiprocessing.Pool, so that we
        # don't block the main thread.
        self.pool = multiprocessing.Pool()
        res = self.pool.imap_unordered(hook.run_command, zip(hook.commands, itertools.repeat(text)))
        # We won't add more tasks to this pool, so close it.
        self.pool.close()

        # Accumulate running processes so that we can check and
        # terminate them neatly later. We also need to keep a running
        # tally of the processes we execute, since res repeats
        # infinitely if processes don't halt.
        #
        # Therefore self.running[hook] = (tally, process_iterable)
        if self.running.get(hook.cause, None):
            self.running[hook] = (self.running[hook][0] + len(hook.commands),
                                  itertools.chain(self.running[hook][1], res))
        else:
            self.running[hook] = (len(hook.commands), res)

    # Terminate all launched hook processes. May block the main thread
    # for a little while.
    #
    def finish(self):
        for hook, processes in self.running.items():
            length, processes = processes

            # We need to keep track of how many elements we have
            # processed - processes may repeat infinitely.
            iterations = 0
            while True:
                iterations += 1

                # Try and get the output for the next process, giving
                # it a second to finish.
                try:
                    command, exit_code, out = processes.next(1)
                except StopIteration:
                    break
                except multiprocessing.context.TimeoutError:
                    message = Message(None, MessageType.ERROR,
                                      "A command for hook '{}' is still "
                                      "running and will be killed"
                                      .format(hook.cause))
                    self.context._message(message)

                    if iterations >= length:
                        break
                    else:
                        continue

                # If the command failed, print something to help debug
                if exit_code != 0:
                    message = Message(None, MessageType.ERROR,
                                      "Command '{}' failed for hook '{}'"
                                      .format(command, hook.cause),
                                      detail=out.decode('utf-8') or "No output")
                    self.context._message(message)

        # Terminate all remaining processes in the pool.
        if self.pool is not None:
            self.pool.terminate()
            self.pool.join()


# Accumulates hook data and helper functions
#
class Hook():
    def __init__(self, cause, commands, project, element):
        self.cause = cause
        self.element = element
        self.project = project
        self.commands = commands
        self.running = []

    def run_command(self, args):
        command, text = args

        # Initialize variables that may not be initialized if we terminate early
        out = ""
        process = None

        # Ensure that the inner command is properly quoted
        command = shlex.quote(command)
        argv = shlex.split("/bin/bash -c {}".format(command))

        def kill_proc():
            if process:
                proc = psutil.Process(process.pid)
                proc.terminate()

                try:
                    proc.wait(1)
                    return
                except psutil.TimeoutExpired:
                    pass

                _kill_process_tree(process.pid)

        # Execute the command, ensuring it is killed if the parent
        # process dies.
        with _signals.terminator(kill_proc):
            process = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT
            )

            out, _ = process.communicate(input=bytes(text, 'utf-8'))

        return (command, process.returncode, out)
