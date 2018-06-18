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
#        Jonathan Maw <jonathan.maw@codethink.co.uk>

"""
ScriptElement - Abstract class for scripting elements
=====================================================
The ScriptElement class is a convenience class one can derive for
implementing elements that stage elements and run command-lines on them.

Any derived classes must write their own configure() implementation, using
the public APIs exposed in this class.

Derived classes must also chain up to the parent method in their preflight()
implementations.


"""

import os
from collections import OrderedDict

from . import Element, ElementError, Scope, SandboxFlags


class ScriptElement(Element):
    __install_root = "/"
    __cwd = "/"
    __root_read_only = False
    __commands = None
    __layout = []

    # The compose element's output is it's dependencies, so
    # we must rebuild if the dependencies change even when
    # not in strict build plans.
    #
    BST_STRICT_REBUILD = True

    # Script artifacts must never have indirect dependencies,
    # so runtime dependencies are forbidden.
    BST_FORBID_RDEPENDS = True

    # This element ignores sources, so we should forbid them from being
    # added, to reduce the potential for confusion
    BST_FORBID_SOURCES = True

    def set_work_dir(self, work_dir=None):
        """Sets the working dir

        The working dir (a.k.a. cwd) is the directory which commands will be
        called from.

        Args:
          work_dir (str): The working directory. If called without this argument
          set, it'll default to the value of the variable ``cwd``.
        """
        if work_dir is None:
            self.__cwd = self.get_variable("cwd") or "/"
        else:
            self.__cwd = work_dir

    def set_install_root(self, install_root=None):
        """Sets the install root

        The install root is the directory which output will be collected from
        once the commands have been run.

        Args:
          install_root(str): The install root. If called without this argument
          set, it'll default to the value of the variable ``install-root``.
        """
        if install_root is None:
            self.__install_root = self.get_variable("install-root") or "/"
        else:
            self.__install_root = install_root

    def set_root_read_only(self, root_read_only):
        """Sets root read-only

        When commands are run, if root_read_only is true, then the root of the
        filesystem will be protected. This is strongly recommended whenever
        possible.

        If this variable is not set, the default permission is read-write.

        Args:
          root_read_only (bool): Whether to mark the root filesystem as
          read-only.
        """
        self.__root_read_only = root_read_only

    def layout_add(self, element, destination):
        """Adds an element-destination pair to the layout.

        Layout is a way of defining how dependencies should be added to the
        staging area for running commands.

        Args:
          element (str): The name of the element to stage, or None. This may be any
                         element found in the dependencies, whether it is a direct
                         or indirect dependency.
          destination (str): The path inside the staging area for where to
                             stage this element. If it is not "/", then integration
                             commands will not be run.

        If this function is never called, then the default behavior is to just
        stage the Scope.BUILD dependencies of the element in question at the
        sandbox root. Otherwise, the Scope.RUN dependencies of each specified
        element will be staged in their specified destination directories.

        .. note::

           The order of directories in the layout is significant as they
           will be mounted into the sandbox. It is an error to specify a parent
           directory which will shadow a directory already present in the layout.

        .. note::

           In the case that no element is specified, a read-write directory will
           be made available at the specified location.
        """
        #
        # Even if this is an empty list by default, make sure that it's
        # instance data instead of appending stuff directly onto class data.
        #
        if not self.__layout:
            self.__layout = []
        self.__layout.append({"element": element,
                              "destination": destination})

    def add_commands(self, group_name, command_list):
        """Adds a list of commands under the group-name.

        .. note::

           Command groups will be run in the order they were added.

        .. note::

           This does not perform substitutions automatically. They must
           be performed beforehand (see
           :func:`~buildstream.element.Element.node_subst_list`)

        Args:
          group_name (str): The name of the group of commands.
          command_list (list): The list of commands to be run.
        """
        if not self.__commands:
            self.__commands = OrderedDict()
        self.__commands[group_name] = command_list

    def __validate_layout(self):
        if self.__layout:
            # Cannot proceeed if layout is used, but none are for "/"
            root_defined = any([(entry['destination'] == '/') for entry in self.__layout])
            if not root_defined:
                raise ElementError("{}: Using layout, but none are staged as '/'"
                                   .format(self))

            # Cannot proceed if layout specifies an element that isn't part
            # of the dependencies.
            for item in self.__layout:
                if item['element']:
                    if not self.search(Scope.BUILD, item['element']):
                        raise ElementError("{}: '{}' in layout not found in dependencies"
                                           .format(self, item['element']))

    def preflight(self):
        # The layout, if set, must make sense.
        self.__validate_layout()

    def get_unique_key(self):
        return {
            'commands': self.__commands,
            'cwd': self.__cwd,
            'install-root': self.__install_root,
            'layout': self.__layout,
            'root-read-only': self.__root_read_only
        }

    def configure_sandbox(self, sandbox):

        # Setup the environment and work directory
        sandbox.set_work_directory(self.__cwd)

        # Setup environment
        sandbox.set_environment(self.get_environment())

        # Mark the artifact directories in the layout
        for item in self.__layout:
            if item['destination'] != '/':
                if item['element']:
                    sandbox.mark_directory(item['destination'], artifact=True)
                else:
                    sandbox.mark_directory(item['destination'])

        # Tell the sandbox to mount the install root
        sandbox.mark_directory(self.__install_root)

    def stage(self, sandbox):

        # Stage the elements, and run integration commands where appropriate.
        if not self.__layout:
            # if no layout set, stage all dependencies into /
            for build_dep in self.dependencies(Scope.BUILD, recurse=False):
                with self.timed_activity("Staging {} at /"
                                         .format(build_dep.name), silent_nested=True):
                    build_dep.stage_dependency_artifacts(sandbox, Scope.RUN, path="/")

            for build_dep in self.dependencies(Scope.BUILD, recurse=False):
                with self.timed_activity("Integrating {}".format(build_dep.name), silent_nested=True):
                    for dep in build_dep.dependencies(Scope.RUN):
                        dep.integrate(sandbox)
        else:
            # If layout, follow its rules.
            for item in self.__layout:

                # Skip layout members which dont stage an element
                if not item['element']:
                    continue

                element = self.search(Scope.BUILD, item['element'])
                if item['destination'] == '/':
                    with self.timed_activity("Staging {} at /".format(element.name),
                                             silent_nested=True):
                        element.stage_dependency_artifacts(sandbox, Scope.RUN)
                else:
                    with self.timed_activity("Staging {} at {}"
                                             .format(element.name, item['destination']),
                                             silent_nested=True):
                        real_dstdir = os.path.join(sandbox.get_directory(),
                                                   item['destination'].lstrip(os.sep))
                        os.makedirs(os.path.dirname(real_dstdir), exist_ok=True)
                        element.stage_dependency_artifacts(sandbox, Scope.RUN, path=item['destination'])

            for item in self.__layout:

                # Skip layout members which dont stage an element
                if not item['element']:
                    continue

                element = self.search(Scope.BUILD, item['element'])

                # Integration commands can only be run for elements staged to /
                if item['destination'] == '/':
                    with self.timed_activity("Integrating {}".format(element.name),
                                             silent_nested=True):
                        for dep in element.dependencies(Scope.RUN):
                            dep.integrate(sandbox)

        os.makedirs(os.path.join(sandbox.get_directory(), self.__install_root.lstrip(os.sep)),
                    exist_ok=True)

    def assemble(self, sandbox):

        for groupname, commands in self.__commands.items():
            with self.timed_activity("Running '{}'".format(groupname)):
                for cmd in commands:
                    self.status("Running command", detail=cmd)
                    # Note the -e switch to 'sh' means to exit with an error
                    # if any untested command fails.
                    exitcode = sandbox.run(['sh', '-c', '-e', cmd + '\n'],
                                           SandboxFlags.ROOT_READ_ONLY if self.__root_read_only else 0)
                    if exitcode != 0:
                        raise ElementError("Command '{}' failed with exitcode {}".format(cmd, exitcode))

        # Return where the result can be collected from
        return self.__install_root


def setup():
    return ScriptElement
