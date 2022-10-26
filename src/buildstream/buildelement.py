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

Built-in functionality
----------------------
The BuildElement base class provides built in functionality that could be
overridden by the individual plugins.

This section will give a brief summary of how some of the common features work,
some of them or the variables they use will be further detailed in the following
sections.


The `strip-binaries` variable
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The `strip-binaries` variable is by default **empty**. You need to use the
appropiate commands depending of the system you are building.
If you are targetting Linux, ones known to work are the ones used by the
`freedesktop-sdk <https://freedesktop-sdk.io/>`_, you can take a look to them in their
`project.conf <https://gitlab.com/freedesktop-sdk/freedesktop-sdk/blob/freedesktop-sdk-18.08.21/project.conf#L74>`_


Location for staging dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The BuildElement supports the "location" :term:`dependency configuration <Dependency configuration>`,
which means you can use this configuration for any BuildElement class.

The "location" configuration defines where the dependency will be staged in the
build sandbox.

**Example:**

Here is an example of how one might stage some dependencies into
an alternative location while staging some elements in the sandbox root.

.. code:: yaml

   # Stage these build dependencies in /opt
   #
   build-depends:
   - baseproject.bst:opt-dependencies.bst
     config:
       location: /opt

   # Stage these tools in "/" and require them as
   # runtime dependencies.
   depends:
   - baseproject.bst:base-tools.bst

.. note::

    The order of dependencies specified is not significant.

    The staging locations will be sorted so that elements are staged in parent
    directories before subdirectories.


Location for running commands
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The ``command-subdir`` variable sets where commands will be executed,
and the directory will be created automatically if it does not exist.

The ``command-subdir`` is a relative path from ``%{build-root}``, and
cannot be a parent or adjacent directory, it must expand to a subdirectory
of ``${build-root}``.


Location for configuring the project
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The ``conf-root`` is the location that specific build elements can use to look for build configuration files.
This is used by elements such as `autotools <https://apache.github.io/buildstream-plugins/elements/autotools.html>`_,
`cmake <https://apache.github.io/buildstream-plugins/elements/cmake.html>`_,
`meson <https://apache.github.io/buildstream-plugins/elements/meson.html>`_,
`setuptools <https://apache.github.io/buildstream-plugins/elements/setuptools.html>`_ and
`pip <https://apache.github.io/buildstream-plugins/elements/pip.html>`_.

The default value of ``conf-root`` is defined by default as ``.``. This means that if
the ``conf-root`` is not explicitly set to another directory, the configuration
files are expected to be found in ``command-subdir``.


Separating source and build directories
'''''''''''''''''''''''''''''''''''''''
A typical example of using ``conf-root`` is when performing
`autotools <https://apache.github.io/buildstream-plugins/elements/autotools.html>`_ builds
where your source directory is separate from your build directory.

This can be achieved in build elements which use ``conf-root`` as follows:

.. code:: yaml

   variables:
     # Specify that build configuration scripts are found in %{build-root}
     conf-root: "%{build-root}"

     # The build will run in the `_build` subdirectory
     command-subdir: _build


Install Location
~~~~~~~~~~~~~~~~
Build elements must install the build output to the directory defined by ``install-root``.

You need not set or change the ``install-root`` variable as it will be defined
automatically on your behalf, and it is used to collect build output when creating
the resulting artifacts.

It is important to know about ``install-root`` in order to write your own
custom install instructions, for example the
`cmake <https://apache.github.io/buildstream-plugins/elements/cmake.html>`_
element will use it to specify the ``DESTDIR``.


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

        # FIXME: Currently this forcefully validates configurations
        #        for all BuildElement subclasses so they are unable to
        #        extend the configuration

        for dep in dependencies:
            # Determine the location to stage each element, default is "/"
            location = "/"
            if dep.config:
                dep.config.validate_keys(["location"])
                location = dep.config.get_str("location")
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
        sandbox.set_environment(self.get_environment())

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
