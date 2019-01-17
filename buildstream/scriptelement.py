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

from . import Element, SandboxFlags
from ._sysroot_dependency_loader import SysrootDependencyLoader, SysrootHelper


class ScriptElement(Element):
    __install_root = "/"
    __cwd = "/"
    __root_read_only = False
    __commands = None

    # The compose element's output is its dependencies, so
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

    COMMON_CONFIG_KEYS = SysrootHelper.CONFIG_KEYS

    DEPENDENCY_LOADER = SysrootDependencyLoader

    def configure(self, node):

        self.__stage_all = True  # pylint: disable=attribute-defined-outside-init
        self.__sysroots = SysrootHelper(self, node)  # pylint: disable=attribute-defined-outside-init

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
        self.__stage_all = False  # pylint: disable=attribute-defined-outside-init
        self.__sysroots.layout_add(element, destination)

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

    def preflight(self):
        self.__sysroots.validate()

    def get_unique_key(self):
        return {
            'commands': self.__commands,
            'cwd': self.__cwd,
            'install-root': self.__install_root,
            'layout': self.__sysroots.get_unique_key(),
            'root-read-only': self.__root_read_only
        }

    def configure_sandbox(self, sandbox):

        # Setup the environment and work directory
        sandbox.set_work_directory(self.__cwd)

        # Setup environment
        sandbox.set_environment(self.get_environment())

        self.__sysroots.configure_sandbox(sandbox, [self.__install_root])

    def stage(self, sandbox):

        self.__sysroots.stage(sandbox, self.__stage_all)

        install_root_path_components = self.__install_root.lstrip(os.sep).split(os.sep)
        sandbox.get_virtual_directory().descend(install_root_path_components, create=True)

    def assemble(self, sandbox):

        flags = SandboxFlags.NONE
        if self.__root_read_only:
            flags |= SandboxFlags.ROOT_READ_ONLY

        with sandbox.batch(flags, collect=self.__install_root):
            for groupname, commands in self.__commands.items():
                with sandbox.batch(flags, label="Running '{}'".format(groupname)):
                    for cmd in commands:
                        # Note the -e switch to 'sh' means to exit with an error
                        # if any untested command fails.
                        sandbox.run(['sh', '-c', '-e', cmd + '\n'],
                                    flags,
                                    label=cmd)

        # Return where the result can be collected from
        return self.__install_root


def setup():
    return ScriptElement
