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
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

"""The BuildElement class is a convenience element one can derive from for
implementing the most common case of element.


Description of assemble activities
----------------------------------
This element will perform the following steps to assemble an element:

Stage dependencies
~~~~~~~~~~~~~~~~~~
The dependencies in the :func:`Scope.BUILD <buildstream.element.Scope.BUILD>`
scope will be staged at the root of the sandbox

Integrate dependencies
~~~~~~~~~~~~~~~~~~~~~~
The integration commands taken from the ``bst`` public domain of each dependency
will be run in the sandbox to create and update caches. Typically ``ldconfig``
among other things is run in this step.

Stage sources
~~~~~~~~~~~~~
:mod:`Sources <buildstream.source>` are now staged according to their configuration
into the ``%{build-root}`` directory (normally ``/buildstream/build``) inside the sandbox.

Run commands
~~~~~~~~~~~~
Commands are now run in the sandbox.

Commands are taken from the element configuration specified by the given
:mod:`BuildElement <buildstream.buildelement>` subclass, which can in turn be
overridden by the user in element declarations (``.bst`` files).

Commands are run in the following order:

* ``configure-commands``: Commands to configure how the element will build
* ``build-commands``: Commands to build the element
* ``install-commands``: Commands to install the results into ``%{install-root}``
* ``strip-commands``: Commands to strip debugging symbols installed binaries

In addition to the above command domains, each command list is checked
for a ``pre-`` and ``post-`` command domain. So for instance, an element
declaration can append or prepend commands without overriding the existing
defaults provided by the element type

**Example**

.. code:: yaml

  config:
    pre-configure-commands:
    - echo "Do something before default configure-commands"

**Working Directory**

Note that by default the working directory is where the sources are staged in
``%{build-root}``, but this can be overridden to build inside of a subdirectory
of the build directory using the ``command-subdir`` variable in an element
declaration. e.g.:

.. code:: yaml

  variables:
    command-subdir: src

The above fragment will cause all commands to be run in the ``src/`` subdirectory
of the staged sources.


Result collection
~~~~~~~~~~~~~~~~~
Finally, the resulting build *artifact* is collected from the the ``%{install-root}``
directory (which is normally configured as ``/buildstream/install``) inside the sandbox.

All build elements must install into the ``%{install-root}`` using whatever
semantic the given build system provides to do this. E.g. for standard autotools
packages we simply do ``make DESTDIR=%{install-root} install``.
"""

import os
from . import Element, Scope, ElementError
from . import SandboxFlags

_command_steps = ['bootstrap-commands',
                  'configure-commands',
                  'build-commands',
                  'test-commands',
                  'install-commands',
                  'strip-commands']
_command_prefixes = ['pre-', '', 'post-']


class BuildElement(Element):

    def configure(self, node):

        self.commands = {}
        command_names = [prefix + step for step in _command_steps for prefix in _command_prefixes]

        # FIXME: Currently this forcefully validates configurations
        #        for all BuildElement subclasses so they are unable to
        #        extend the configuration
        self.node_validate(node, command_names)

        for command_name in command_names:
            self.commands[command_name] = self._get_commands(node, command_name)

    def preflight(self):
        pass

    def get_unique_key(self):
        dictionary = {}

        for command_name, command_list in self.commands.items():
            dictionary[command_name] = command_list

        # Specifying notparallel for a given element effects the
        # cache key, while having the side effect of setting max-jobs to 1,
        # which is normally automatically resolved and does not effect
        # the cache key.
        variables = self._get_variables()
        if self.node_get_member(variables.variables, bool, 'notparallel', default_value=False):
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
        for step in _command_steps:
            for prefix in _command_prefixes:
                command_name = prefix + step
                commands = self.commands[command_name]
                if not commands:
                    continue

                with self.timed_activity("Running %s" % command_name):
                    for cmd in commands:
                        self.status("Running %s" % command_name, detail=cmd)

                        # Note the -e switch to 'sh' means to exit with an error
                        # if any untested command fails.
                        #
                        exitcode = sandbox.run(['sh', '-c', '-e', cmd + '\n'],
                                               SandboxFlags.ROOT_READ_ONLY)
                        if exitcode != 0:
                            raise ElementError("Command '{}' failed with exitcode {}".format(cmd, exitcode))

        # Return the payload, this is configurable but is generally
        # always the /buildstream/install directory
        return self.get_variable('install-root')

    def _get_commands(self, node, name):
        list_node = self.node_get_member(node, list, name, default_value=[])
        commands = []

        for i in range(len(list_node)):
            command = self.node_subst_list_element(node, name, [i])
            commands.append(command)

        return commands

    def generate_script(self):
        script = ""
        for step in _command_steps:
            for prefix in _command_prefixes:
                command_name = prefix + step
                commands = self.commands[command_name]

                for cmd in commands:
                    script += "(set -ex; {}\n) || exit 1\n".format(cmd)

        return script
