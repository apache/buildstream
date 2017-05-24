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

"""Script element

This element allows one to run some commands to mutate the
input and create some output.

As with build elements, the output created by a script element is
collected from the ``%{install-root}`` directory.

The default configuration and possible options are as such:
  .. literalinclude:: ../../../buildstream/plugins/elements/script.yaml
     :language: yaml
"""

import os
from buildstream import utils
from buildstream import Element, ElementError, Scope
from buildstream import SandboxFlags


# Element implementation for the 'script' kind.
class ScriptElement(Element):

    def configure(self, node):
        self.base_dep = self.node_get_member(node, str, 'base')
        self.input_dep = self.node_get_member(node, str, 'input', '') or None
        self.stage_mode = self.node_get_member(node, str, 'stage-mode')
        self.collect = self.node_subst_member(node, 'collect', '%{install-root}')

        # Assert stage mode is valid
        if self.stage_mode and self.stage_mode not in ['build', 'install']:
            p = self.node_provenance(node, 'stage-mode')
            raise ElementError("{}: Stage mode must be either 'build' or 'install'"
                               .format(p))

        # Collect variable substituted commands
        self.commands = []
        command_list = self.node_get_member(node, list, 'commands', default_value=[])
        for i in range(len(command_list)):
            self.commands.append(
                self.node_subst_list_element(node, 'commands', [i])
            )

        # To be resolved in preflight when the pipeline is built
        self.base_elt = None
        self.input_elt = None

    def preflight(self):

        # Assert that the user did not list any runtime dependencies
        runtime_deps = list(self.dependencies(Scope.RUN, recurse=False))
        if runtime_deps:
            raise ElementError("{}: Only build type dependencies supported by script elements"
                               .format(self))

        # Assert that the user did not specify any sources, as they will
        # be ignored by this element type anyway
        sources = list(self.sources())
        if sources:
            raise ElementError("Script elements may not have sources")

        # Assert that a base and an input were specified
        if not self.base_dep:
            raise ElementError("{}: No base dependencies were specified".format(self))

        # Now resolve the base and input elements
        self.base_elt = self.search(Scope.BUILD, self.base_dep)
        if self.input_dep:
            self.input_elt = self.search(Scope.BUILD, self.input_dep)

        if self.base_elt is None:
            raise ElementError("{}: Could not find base dependency {}".format(self, self.base_dep))

    def get_unique_key(self):
        return {
            'commands': self.commands,
            'base': self.base_dep,
            'input': self.input_dep,
            'stage-mode': self.stage_mode,
            'collect': self.collect
        }

    def assemble(self, sandbox):

        directory = sandbox.get_directory()
        environment = self.get_environment()

        # Stage the base in the sandbox root
        with self.timed_activity("Staging {} as base".format(self.base_dep), silent_nested=True):
            self.base_elt.stage_dependencies(sandbox, Scope.RUN)

        # Run any integration commands on the base
        with self.timed_activity("Integrating sandbox", silent_nested=True):
            for dep in self.base_elt.dependencies(Scope.RUN):
                dep.integrate(sandbox)

        # Ensure some directories we'll need
        cmd_dir = '/'
        if self.stage_mode:
            os.makedirs(os.path.join(directory,
                                     'buildstream',
                                     'build'), exist_ok=True)
            os.makedirs(os.path.join(directory,
                                     'buildstream',
                                     'install'), exist_ok=True)

            # Stage the input
            input_dir = os.path.join(os.sep, 'buildstream', self.stage_mode)
            cmd_dir = input_dir
            with self.timed_activity("Staging {} as input at {}"
                                     .format(self.input_dep, input_dir), silent_nested=True):
                self.input_elt.stage_dependencies(sandbox, Scope.RUN, path=input_dir)

        # Run the scripts
        with self.timed_activity("Running script commands"):
            for cmd in self.commands:
                self.status("Running command", detail=cmd)

                # Note the -e switch to 'sh' means to exit with an error
                # if any untested command fails.
                exitcode = sandbox.run(['sh', '-c', '-e', cmd + '\n'],
                                       0,
                                       cwd=cmd_dir,
                                       env=environment)
                if exitcode != 0:
                    raise ElementError("Command '{}' failed with exitcode {}".format(cmd, exitcode))

        # Return the install dir
        return self.collect


# Plugin entry point
def setup():
    return ScriptElement
