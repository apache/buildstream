..
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.


.. _core_buildelement_builtins:

BuildElement - Built-in functionality
=====================================
The :doc:`manual <elements/manual>` core plugin and various common element plugins
available in other repositories are based on the :mod:`BuildElement <buildstream.buildelement>` base class,
which provides built in functionality that could be overridden by the individual plugins.

This page will give a brief summary of how some of the common features work,
some of them or the variables they use will be further detailed in the
:doc:`API reference <buildstream.buildelement>`.

.. contents::
   :local:

Build steps
~~~~~~~~~~~

The sandbox is prepared
-----------------------

The sandbox is prepared as a temporary filesystem, where build dependencies
are staged, along with their own runtime dependencies. This happens in
an abstract state, which can quickly spot repeated files and :ref:`overlaps <handling_files_overlaps>`.

When a dependency is being staged, the produced artifact is added from the root
(``/``). This can be changed using the ``location:`` attribute, as described in
:ref:`location for staging dependencies <core_buildelement_dep_location>`.

The sandbox root directory with the staged dependencies is read-only.

After the dependencies are staged, BuildStream stages the sources in the
``build-root`` location. The actual location of this differs slightly
depending on the project file structure, which is why it is common to
see elements use the variable ``%{build-root}`` which resolves to the
correct location.

Configure and build commands
----------------------------

Now that all dependencies and sources are staged in a temporary filesystem,
BuildBox uses this filesystem as root filesystem for the build :ref:`sandbox <sandboxing>`.

The first commands to be run are configure commands and it is
recommended to include things like moving the sources about, generating
config files and other “configure” related actions into this section.
These should be the commands that can only be run once (for example a
folder can only be moved once), this is due to BuildStream
workspaces.

.. note::

   **Workspaces and configure commands**

   When a :ref:`workspace <developing_workspaces>` is opened,
   it stages all the sources for the indicated
   element locally, then when doing a build of that element it uses these local
   sources instead of pulling in fresh sources. Builds using workspaces only
   run configure commands once, and any subsequent builds using the same
   workspace will skip the configure commands step, therefore steps of the
   build that can't be executed multiple times (without re-staging sources)
   should be added to configure commands.

After configure commands are run, then build commands are next. Build
commands are intended to contain the actual build process, for example
if the build uses ``make`` then this stage should run the
``make target`` command.

Install commands and caching artifacts
--------------------------------------

Install and strip commands are the final commands that are run before BuildStream
collects the artifacts and closes the build sandbox. Install commands
should mainly be comprised of moving the built artifacts from the
``${build-root}`` to the ``${install-root}``.

The `install-commands` should not clean up any of the sources, as they can be stored as a _buildtree_, which allows for introspection after the build.

Directories can be created under the install location, for example
``%{install-root}/example/``, and these will be maintained when another
element depends on this one, for example this will become
``/example/``.

Strip commands are run after install commands to strip debugging symbols of
binaries in the install root. Plugins are expected to use the ``strip-binaries``
variable as strip command. That project variable is by default **empty**.
You need to use the appropiate commands depending of the system you are building.
If you are targeting Linux, ones known to work are the ones used by the
`freedesktop-sdk <https://freedesktop-sdk.io/>`_, you can take a look to them in their
`project.conf <https://gitlab.com/freedesktop-sdk/freedesktop-sdk/blob/freedesktop-sdk-18.08.21/project.conf#L74>`_

The contents of the install root are cached. BuildStream caches the
produced artifact to reduce the need to rebuild elements, instead it can
pull from this artifact cache. It will only rebuild an element if the
element file changes, or if the dependencies for an element changes.

.. note::

   BuildStream will also **cache build errors**, and if no file has changed
   (including the dependencies) then BuildStream will display this cached error,
   without attempting a rebuild. This is sometimes not the desired behaviour,
   especially if the error was caused by a remote issue, like a source site
   being temporarily unavailable. To force an attempted build use the
   ``-r``/``--retry-failed`` option, documented :ref:`here <invoking_build>`.


.. _core_buildelement_dep_location:

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


`digest-environment` for dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The BuildElement supports the ``digest-environment`` :term:`dependency configuration <Dependency configuration>`,
which sets the specified environment variable in the build sandbox to the CAS digest
corresponding to a directory that contains all dependencies that are configured
with the same ``digest-environment``.

This is useful for REAPI clients in the sandbox such as `recc <https://buildgrid.gitlab.io/recc>`_,
see ``remote-apis-socket`` in the :ref:`sandbox configuration <format_sandbox>`.

**Example:**

Here is an example of how to set the environment variable `GCC_DIGEST` to the
CAS digest of a directory that contains ``gcc.bst`` and its runtime dependencies.
The ``libpony.bst`` dependency will not be included in that CAS directory.

.. code:: yaml

   build-depends:
   - baseproject.bst:gcc.bst
     config:
       digest-environment: GCC_DIGEST
   - libpony.bst


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
---------------------------------------
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
