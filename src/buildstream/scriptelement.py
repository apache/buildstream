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
from typing import List, Optional, TYPE_CHECKING

from .element import Element

if TYPE_CHECKING:
    from typing import Dict, Tuple


class ScriptElement(Element):
    __install_root = "/"
    __cwd = "/"
    __root_read_only = False
    __commands = None  # type: OrderedDict[str, List[str]]
    __layout = {}  # type: Dict[str, List[Tuple[Element, str]]]

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

    #############################################################
    #                       Public Methods                      #
    #############################################################

    def set_work_dir(self, work_dir: Optional[str] = None) -> None:
        """Sets the working dir

        The working dir (a.k.a. cwd) is the directory which commands will be
        called from.

        Args:
           work_dir: The working directory. If called without this argument
                     set, it'll default to the value of the variable ``cwd``.
        """
        if work_dir is None:
            self.__cwd = self.get_variable("cwd") or "/"
        else:
            self.__cwd = work_dir

    def set_install_root(self, install_root: Optional[str] = None) -> None:
        """Sets the install root

        The install root is the directory which output will be collected from
        once the commands have been run.

        Args:
           install_root: The install root. If called without this argument
                         set, it'll default to the value of the variable ``install-root``.
        """
        if install_root is None:
            self.__install_root = self.get_variable("install-root") or "/"
        else:
            self.__install_root = install_root

    def set_root_read_only(self, root_read_only: bool) -> None:
        """Sets root read-only

        When commands are run, if root_read_only is true, then the root of the
        filesystem will be protected. This is strongly recommended whenever
        possible.

        If this variable is not set, the default permission is read-write.

        Args:
           root_read_only: Whether to mark the root filesystem as read-only.
        """
        self.__root_read_only = root_read_only

    def layout_add(self, element: Element, dependency_path: str, location: str) -> None:
        """Adds an element to the layout.

        Layout is a way of defining how dependencies should be added to the
        staging area for running commands.

        Args:
           element (Element): The element to stage.
           dependency_path (str): The element relative path to the dependency, usually obtained via
                                  :attr:`the dependency configuration <buildstream.element.DependencyConfiguration.path>`
           location (str): The path inside the staging area for where to
                          stage this element. If it is not "/", then integration
                          commands will not be run.

        If this function is never called, then the default behavior is to just
        stage the build dependencies of the element in question at the
        sandbox root. Otherwise, the specified elements including their
        runtime dependencies will be staged in their respective locations.

        .. note::

           The order of directories in the layout is not significant.

           The paths in the layout will be sorted so that elements are staged in parent
           directories before subdirectories.

           The elements for each respective staging directory in the layout will be staged
           in the predetermined deterministic staging order.
        """
        #
        # Even if this is an empty dict by default, make sure that it is
        # instance data instead of appending stuff directly onto class data.
        #
        if not self.__layout:
            self.__layout = {}

        # Get or create the element list
        try:
            element_list = self.__layout[location]
        except KeyError:
            element_list = []
            self.__layout[location] = element_list

        element_list.append((element, dependency_path))

    def add_commands(self, group_name: str, command_list: List[str]) -> None:
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

    #############################################################
    #             Abstract Method Implementations               #
    #############################################################
    def preflight(self):
        pass

    def get_unique_key(self):
        sorted_locations = sorted(self.__layout)
        layout_key = {
            location: [dependency_path for _, dependency_path in self.__layout[location]]
            for location in sorted_locations
        }
        return {
            "commands": self.__commands,
            "cwd": self.__cwd,
            "install-root": self.__install_root,
            "layout": layout_key,
            "root-read-only": self.__root_read_only,
        }

    def configure_sandbox(self, sandbox):

        # Setup the environment and work directory
        sandbox.set_work_directory(self.__cwd)

        # Setup environment
        sandbox.set_environment(self.get_environment())

        # Mark the install root
        sandbox.mark_directory(self.__install_root)

    def stage(self, sandbox):

        # If self.layout_add() was never called, do the default staging of
        # everything in "/" and run the integration commands
        if not self.__layout:

            with self.timed_activity("Staging dependencies", silent_nested=True):
                self.stage_dependency_artifacts(sandbox)

            with sandbox.batch(label="Integrating sandbox"):
                for dep in self.dependencies():
                    dep.integrate(sandbox)

        else:
            # First stage it all
            #
            sorted_locations = sorted(self.__layout)

            for location in sorted_locations:
                with self.timed_activity("Staging dependencies at: {}".format(location), silent_nested=True):
                    element_list = [element for element, _ in self.__layout[location]]
                    self.stage_dependency_artifacts(sandbox, element_list, path=location)

            # Now integrate any elements staged in the root
            #
            root_list = self.__layout.get("/", None)
            if root_list:
                element_list = [element for element, _ in root_list]
                with sandbox.batch(), self.timed_activity("Integrating sandbox", silent_nested=True):
                    for dep in self.dependencies(element_list):
                        dep.integrate(sandbox)

        # Ensure the install root exists
        #
        sandbox.get_virtual_directory().open_directory(self.__install_root.lstrip(os.sep), create=True)

    def assemble(self, sandbox):
        with sandbox.batch(root_read_only=self.__root_read_only, collect=self.__install_root):
            for groupname, commands in self.__commands.items():
                with sandbox.batch(root_read_only=self.__root_read_only, label="Running '{}'".format(groupname)):
                    for cmd in commands:
                        # Note the -e switch to 'sh' means to exit with an error
                        # if any untested command fails.
                        sandbox.run(["sh", "-c", "-e", cmd + "\n"], root_read_only=self.__root_read_only, label=cmd)

            # Empty the build directory after a successful build to avoid the
            # overhead of capturing the build directory.
            self.run_cleanup_commands(sandbox)

        # Return where the result can be collected from
        return self.__install_root


def setup():
    return ScriptElement
