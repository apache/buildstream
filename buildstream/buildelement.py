#
#  Copyright (C) 2016 Codethink Limited
#  Copyright (C) 2018 Bloomberg Finance LP
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
"""
BuildElement - Abstract class for build elements
================================================
The BuildElement class is a convenience element one can derive from for
implementing the most common case of element.


Abstract method implementations
-------------------------------

Element.configure_sandbox()
~~~~~~~~~~~~~~~~~~~~~~~~~~~
In :func:`Element.configure_sandbox() <buildstream.element.Element.configure_sandbox>`,
the BuildElement will ensure that the sandbox locations described by the ``%{build-root}``
and ``%{install-root}`` variables are marked and will be mounted read-write for the
:func:`assemble phase<buildstream.element.Element.configure_sandbox>`.

The working directory for the sandbox will be configured to be the ``%{build-root}``,
unless the ``%{command-subdir}`` variable is specified for the element in question,
in which case the working directory will be configured as ``%{build-root}/%{command-subdir}``.


Element.stage()
~~~~~~~~~~~~~~~
In :func:`Element.stage() <buildstream.element.Element.stage>`, the BuildElement
will do the following operations:

* Stage all the dependencies in the :func:`Scope.BUILD <buildstream.element.Scope.BUILD>`
  scope into the sandbox root.

* Run the integration commands for all staged dependencies using
  :func:`Element.integrate() <buildstream.element.Element.integrate>`

* Stage any Source on the given element to the ``%{build-root}`` location
  inside the sandbox, using
  :func:`Element.stage_sources() <buildstream.element.Element.integrate>`


Element.prepare()
~~~~~~~~~~~~~~~~~
In :func:`Element.prepare() <buildstream.element.Element.prepare>`,
the BuildElement will run ``configure-commands``, which are used to
run one-off preparations that should not be repeated for a single
build directory.


Element.assemble()
~~~~~~~~~~~~~~~~~~
In :func:`Element.assemble() <buildstream.element.Element.assemble>`, the
BuildElement will proceed to run sandboxed commands which are expected to be
found in the element configuration.

Commands are run in the following order:

* ``build-commands``: Commands to build the element
* ``install-commands``: Commands to install the results into ``%{install-root}``
* ``strip-commands``: Commands to strip debugging symbols installed binaries

The result of the build is expected to end up in ``%{install-root}``, and
as such; Element.assemble() method will return the ``%{install-root}`` for
artifact collection purposes.
"""

import os
from . import Element, Scope, ElementError
from . import SandboxFlags


# This list is preserved because of an unfortunate situation, we
# need to remove these older commands which were secret and never
# documented, but without breaking the cache keys.
_legacy_command_steps = ['bootstrap-commands',
                         'configure-commands',
                         'build-commands',
                         'test-commands',
                         'install-commands',
                         'strip-commands']

_command_steps = ['configure-commands',
                  'build-commands',
                  'install-commands',
                  'strip-commands']


class BuildElement(Element):

    #############################################################
    #             Abstract Method Implementations               #
    #############################################################
    def configure(self, node):

        self.__commands = {}

        # FIXME: Currently this forcefully validates configurations
        #        for all BuildElement subclasses so they are unable to
        #        extend the configuration
        self.node_validate(node, _command_steps)

        for command_name in _legacy_command_steps:
            if command_name in _command_steps:
                self.__commands[command_name] = self.__get_commands(node, command_name)
            else:
                self.__commands[command_name] = []

    def preflight(self):
        pass

    def get_unique_key(self):
        dictionary = {}

        for command_name, command_list in self.__commands.items():
            dictionary[command_name] = command_list

        # Specifying notparallel for a given element effects the
        # cache key, while having the side effect of setting max-jobs to 1,
        # which is normally automatically resolved and does not effect
        # the cache key.
        if self.get_variable('notparallel'):
            dictionary['notparallel'] = True

        return dictionary

    def configure_sandbox(self, sandbox):
        build_root = self.get_variable('build-root')
        install_root = self.get_variable('install-root')

        # Tell the sandbox to mount the build root and install root
        sandbox.mark_directory(build_root)
        sandbox.mark_directory(install_root)

        # Allow running all commands in a specified subdirectory
        command_subdir = self.get_variable('command-subdir')
        if command_subdir:
            command_dir = os.path.join(build_root, command_subdir)
        else:
            command_dir = build_root
        sandbox.set_work_directory(command_dir)

        # Setup environment
        sandbox.set_environment(self.get_environment())

    def stage(self, sandbox):

        # Stage deps in the sandbox root
        with self.timed_activity("Staging dependencies", silent_nested=True):
            self.stage_dependency_artifacts(sandbox, Scope.BUILD)

        # Run any integration commands provided by the dependencies
        # once they are all staged and ready
        with self.timed_activity("Integrating sandbox"):
            for dep in self.dependencies(Scope.BUILD):
                dep.integrate(sandbox)

        # Stage sources in the build root
        self.stage_sources(sandbox, self.get_variable('build-root'))

    def assemble(self, sandbox):

        # Run commands
        for command_name in _command_steps:
            commands = self.__commands[command_name]
            if not commands or command_name == 'configure-commands':
                continue

            with self.timed_activity("Running {}".format(command_name)):
                for cmd in commands:
                    self.__run_command(sandbox, cmd, command_name)

        # %{install-root}/%{build-root} should normally not be written
        # to - if an element later attempts to stage to a location
        # that is not empty, we abort the build - in this case this
        # will almost certainly happen.
        staged_build = os.path.join(self.get_variable('install-root'),
                                    self.get_variable('build-root'))

        if os.path.isdir(staged_build) and os.listdir(staged_build):
            self.warn("Writing to %{install-root}/%{build-root}.",
                      detail="Writing to this directory will almost " +
                      "certainly cause an error, since later elements " +
                      "will not be allowed to stage to %{build-root}.")

        # Return the payload, this is configurable but is generally
        # always the /buildstream-install directory
        return self.get_variable('install-root')

    def prepare(self, sandbox):
        commands = self.__commands['configure-commands']
        if commands:
            with self.timed_activity("Running configure-commands"):
                for cmd in commands:
                    self.__run_command(sandbox, cmd, 'configure-commands')

    def generate_script(self):
        script = ""
        for command_name in _command_steps:
            commands = self.__commands[command_name]

            for cmd in commands:
                script += "(set -ex; {}\n) || exit 1\n".format(cmd)

        return script

    #############################################################
    #                   Private Local Methods                   #
    #############################################################
    def __get_commands(self, node, name):
        list_node = self.node_get_member(node, list, name, [])
        commands = []

        for i in range(len(list_node)):
            command = self.node_subst_list_element(node, name, [i])
            commands.append(command)

        return commands

    def __run_command(self, sandbox, cmd, cmd_name):
        self.status("Running {}".format(cmd_name), detail=cmd)

        # Note the -e switch to 'sh' means to exit with an error
        # if any untested command fails.
        #
        exitcode = sandbox.run(['sh', '-c', '-e', cmd + '\n'],
                               SandboxFlags.ROOT_READ_ONLY)
        if exitcode != 0:
            raise ElementError("Command '{}' failed with exitcode {}".format(cmd, exitcode))
