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
import subprocess
import multiprocessing

# Manages and executes hooks.
#
class Hooks():
    def __init__(self, context):
        self.context = context
        self._hooks = {}

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

        hook.run(text)


# Accumulates hook data and helper functions
#
class Hook():
    def __init__(self, cause, commands, project, element):
        self.cause = cause
        self.element = element
        self.project = project
        self.commands = commands

    def run_command(self, command, text):
        process = subprocess.Popen(
            shlex.split(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # FIXME: Processes launched this way may not be killed when
        # buildstream finishes - should we add a timeout? What does
        # the user expect?
        out, err = process.communicate(input=bytes(text, 'utf-8'))
        # Unfortunately, it appears to be impossible to use this data
        # in our message functions without 'dill'.
        return (process.poll(), out, err)

    def run(self, text):
        pool = multiprocessing.Pool()

        for command in self.commands:
            pool.apply_async(self.run_command, (command, text))
