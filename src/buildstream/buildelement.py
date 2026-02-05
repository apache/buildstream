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
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
"""
BuildElement - Abstract class for build elements
================================================
The BuildElement class is a convenience element one can derive from for
implementing the most common case of element.


.. _core_buildelement_builtins:

Built-in functionality # TODO: Should we link this to the 'Using BuildElements' section in the docs?
----------------------

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

* Stage all of the build dependencies into the sandbox root.

* Run the integration commands for all staged dependencies using
  :func:`Element.integrate() <buildstream.element.Element.integrate>`

* Stage any Source on the given element to the ``%{build-root}`` location
  inside the sandbox, using
  :func:`Element.stage_sources() <buildstream.element.Element.integrate>`


Element.assemble()
~~~~~~~~~~~~~~~~~~
In :func:`Element.assemble() <buildstream.element.Element.assemble>`, the
BuildElement will proceed to run sandboxed commands which are expected to be
found in the element configuration.

Commands are run in the following order:

* ``configure-commands``: Commands to configure the build scripts
* ``build-commands``: Commands to build the element
* ``install-commands``: Commands to install the results into ``%{install-root}``
* ``strip-commands``: Commands to strip debugging symbols installed binaries

The result of the build is expected to end up in ``%{install-root}``, and
as such; Element.assemble() method will return the ``%{install-root}`` for
artifact collection purposes.

.. note::

   In the case that the element is currently workspaced, the ``configure-commands``
   will only be run in subsequent builds until they succeed at least once, unless
   :ref:`bst workspace reset --soft <invoking_workspace_reset>` is called on the
   workspace to explicitly avoid an incremental build.

"""

import os

from .element import Element


_command_steps = ["configure-commands", "build-commands", "install-commands", "strip-commands"]


class BuildElement(Element):

    #############################################################
    #             Abstract Method Implementations               #
    #############################################################
    def configure(self, node):

        self.__commands = {}  # pylint: disable=attribute-defined-outside-init

        # FIXME: Currently this forcefully validates configurations
        #        for all BuildElement subclasses so they are unable to
        #        extend the configuration
        node.validate_keys(_command_steps)

        self._command_subdir = self.get_variable("command-subdir")  # pylint: disable=attribute-defined-outside-init

        for command_name in _command_steps:
            self.__commands[command_name] = node.get_str_list(command_name, [])

    def configure_dependencies(self, dependencies):

        self.__layout = {}  # pylint: disable=attribute-defined-outside-init
        self.__digest_environment = {}  # pylint: disable=attribute-defined-outside-init

        # FIXME: Currently this forcefully validates configurations
        #        for all BuildElement subclasses so they are unable to
        #        extend the configuration

        for dep in dependencies:
            # Determine the location to stage each element, default is "/"
            location = "/"

            if dep.config:
                dep.config.validate_keys(["digest-environment", "location"])

                location = dep.config.get_str("location", "/")

                digest_var_name = dep.config.get_str("digest-environment", None)

                if digest_var_name is not None:
                    element_list = self.__digest_environment.setdefault(digest_var_name, [])
                    element_list.append((dep.element, dep.path))

            try:
                element_list = self.__layout[location]
            except KeyError:
                element_list = []
                self.__layout[location] = element_list

            element_list.append((dep.element, dep.path))

    def preflight(self):
        pass

    def get_unique_key(self):
        dictionary = {}

        for command_name, command_list in self.__commands.items():
            dictionary[command_name] = command_list

        if self._command_subdir:
            dictionary["command-subdir"] = self._command_subdir

        # Specifying notparallel for a given element effects the
        # cache key, while having the side effect of setting max-jobs to 1,
        # which is normally automatically resolved and does not affect
        # the cache key.
        if self.get_variable("notparallel"):
            dictionary["notparallel"] = True

        # Specify the layout in the key, if any of the elements are not going to
        # be staged in "/"
        #
        if any(location for location in self.__layout if location != "/"):
            sorted_locations = sorted(self.__layout)
            layout_key = {
                location: [dependency_path for _, dependency_path in self.__layout[location]]
                for location in sorted_locations
            }
            dictionary["layout"] = layout_key

        # Specify the layout in the key, if buildstream is to generate an environment
        # variable with the digest
        #
        if self.__digest_environment:
            sorted_envs = sorted(self.__digest_environment)
            digest_key = {
                env: [dependency_path for _, dependency_path in self.__digest_environment[env]] for env in sorted_envs
            }
            dictionary["digest-enviornment"] = digest_key

        return dictionary

    def configure_sandbox(self, sandbox):
        build_root = self.get_variable("build-root")
        install_root = self.get_variable("install-root")

        # Tell the sandbox to mount the build root and install root
        sandbox.mark_directory(build_root)
        sandbox.mark_directory(install_root)

        # Allow running all commands in a specified subdirectory
        if self._command_subdir:
            command_dir = os.path.join(build_root, self._command_subdir)
        else:
            command_dir = build_root
        sandbox.set_work_directory(command_dir)

        # Setup environment
        env = self.get_environment()

        # Add "CAS digest" environment variables
        sorted_envs = sorted(self.__digest_environment)
        for digest_variable in sorted_envs:
            element_list = [element for element, _ in self.__digest_environment[digest_variable]]
            with self.timed_activity(
                f"Staging dependencies for '{digest_variable}' in subsandbox", silent_nested=True
            ), self.subsandbox(sandbox) as subsandbox:
                self.stage_dependency_artifacts(subsandbox, element_list)
                digest = subsandbox.get_virtual_directory()._get_digest()
            env[digest_variable] = "{}/{}".format(digest.hash, digest.size_bytes)

        sandbox.set_environment(env)

    def stage(self, sandbox):

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
            with self.timed_activity("Integrating sandbox", silent_nested=True), sandbox.batch():
                for dep in self.dependencies(element_list):
                    dep.integrate(sandbox)

        # Stage sources in the build root
        self.stage_sources(sandbox, self.get_variable("build-root"))

    def assemble(self, sandbox):

        with sandbox.batch(root_read_only=True, label="Running commands"):

            # We need to ensure that configure-commands are only called
            # once in workspaces, because the changes will persist across
            # incremental builds - not desirable, for example, in the case
            # of autotools, we don't want to run `./configure` a second time
            # in an incremental build if it has succeeded at least once.
            #
            # Here we use an empty file `.bst-prepared` as a marker of whether
            # configure-commands have already completed successfully in a previous build.
            #
            needs_configure = True
            marker_filename = ".bst-prepared"
            commands = self.__commands["configure-commands"]
            if commands:
                if self._get_workspace():
                    vdir = sandbox.get_virtual_directory()
                    buildroot = self.get_variable("build-root")
                    buildroot_vdir = vdir.open_directory(buildroot.lstrip(os.sep))

                    # Marker found, no need to configure
                    if buildroot_vdir.exists(marker_filename):
                        needs_configure = False

            if needs_configure:
                for cmd in commands:
                    self.__run_command(sandbox, cmd)

                # This will serialize a command to create the marker file
                # in the sandbox batch after running configure
                if self._get_workspace():
                    sandbox._create_empty_file(marker_filename)

            # Run commands
            for command_name in _command_steps:
                commands = self.__commands[command_name]
                if not commands or command_name == "configure-commands":
                    continue

                for cmd in commands:
                    self.__run_command(sandbox, cmd)

            # Empty the build directory after a successful build to avoid the
            # overhead of capturing the build directory.
            self.run_cleanup_commands(sandbox)

            # Return the payload, this is configurable but is generally
            # always the /buildstream-install directory
            return self.get_variable("install-root")

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
    def __run_command(self, sandbox, cmd):
        # Note the -e switch to 'sh' means to exit with an error
        # if any untested command fails.
        #
        sandbox.run(["sh", "-c", "-e", cmd + "\n"], root_read_only=True, label=cmd)
