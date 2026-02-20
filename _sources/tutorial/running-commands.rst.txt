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



.. _tutorial_running_commands:

Running commands
================
In :ref:`the first chapter <tutorial_first_project>` we only imported
a file to create an artifact, this time lets run some commands inside
the :ref:`isolated build sandbox <sandboxing>`.

.. note::

   This example is distributed with BuildStream
   in the `doc/examples/running-commands
   <https://github.com/apache/buildstream/tree/master/doc/examples/running-commands>`_
   subdirectory.


Overview
--------
In this chapter, we'll be running commands inside the sandboxed
execution environment and producing build output.

We'll be compiling the following simple C file:


``files/src/hello.c``
~~~~~~~~~~~~~~~~~~~~~
.. literalinclude:: ../../examples/running-commands/files/src/hello.c
   :language: c


And we're going to build it using ``make``, using the following Makefile:


``files/src/Makefile``
~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/running-commands/files/src/Makefile
   :language: Makefile


We'll be using the most fundamental :ref:`build element <plugins_elements>`,
the :mod:`manual <elements.manual>` build element.

The :mod:`manual <elements.manual>` element is the backbone on which all the other
build elements are built, so understanding how it works at this level is helpful.


Project structure
-----------------
In this project we have a ``project.conf``, a directory with some source
code, and 3 element declarations.

Let's first take a peek at what we need to build using :ref:`bst show <invoking_show>`:

.. raw:: html
   :file: ../sessions/running-commands-show-before.html

This time we have loaded a pipeline with 3 elements, let's go over what they do
in detail.


.. _tutorial_running_commands_project_conf:

``project.conf``
~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/running-commands/project.conf
   :language: yaml

Our ``project.conf`` is very much like the last one, except that we
have defined a :ref:`source alias <project_source_aliases>` for ``alpine``.

.. tip::

   Using :ref:`source aliases <project_source_aliases>` for groups of sources
   which are generally hosted together is encouraged. This allows one to globally
   change the access scheme or URL for a group of repositories which belong together.


``elements/base/alpine.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/running-commands/elements/base/alpine.bst
   :language: yaml

This :mod:`import <elements.import>` element uses a :mod:`tar <sources.tar>`
source to download our Alpine Linux tarball to create our base runtime.

This tarball is a sysroot which provides the C runtime libraries
and some programs - this is what will be providing the programs we're
going to run in this example.


``elements/base.bst``
~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/running-commands/elements/base.bst
   :language: yaml

This is just a symbolic :mod:`stack <elements.stack>` element which declares that
anything which depends on it, will implicitly depend on ``base/alpine.bst``.

It is typical to use stack elements in places where the implementing logical
software stack could change, but you rather not have your higher level components
carry knowledge about those changing components.

Any element which :ref:`runtime depends <format_dependencies_types>` on
the ``base.bst`` will now be able to execute programs provided by the imported
``base/alpine.bst`` runtime.


``elements/hello.bst``
~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/running-commands/elements/hello.bst
   :language: yaml

Finally we have the element which executes commands. Looking at the
:mod:`manual <elements.manual>` element's documentation, we can see that
the element configuration exposes four command lists:

* ``configure-commands``

  Commands which are run in preparation of a build. This is where you
  would normally call any configure stage build tools to configure
  the build how you like and generate some files needed for the build.

* ``build-commands``

  Commands to run the build, usually a build system will
  invoke the compiler for you here.

* ``install-commands``

  Commands to install the build results.

  Commands to install the build results into the target system,
  these should install files somewhere under ``%{install-root}``.

* ``strip-commands``

  Commands to doctor the build results after the install.

  Typically this involves stripping binaries of debugging
  symbols or stripping timestamps from build results to ensure
  reproducibility.

.. tip::

   All other :ref:`build elements <core_buildelement_builtins>`
   implement exactly the same command lists too, except that they provide
   default commands specific to invoke the build systems they support.

The :mod:`manual <elements.manual>` element however is the most basic
and does not provide any default commands, so we have instructed it
to use ``make`` to build and install our program.

     
Using the project
-----------------


Build the hello.bst element
~~~~~~~~~~~~~~~~~~~~~~~~~~~
To build the project, run :ref:`bst build <invoking_build>` in the
following way:

.. raw:: html
   :file: ../sessions/running-commands-build.html

Now we've built our hello world program, using ``make``
and the C compiler provided by the Alpine Linux image.

In the :ref:`first chapter <tutorial_first_project>` we observed that the inputs
and output of an element are *directory trees*. In this example, the directory tree
generated by ``base/alpine.bst`` is consumed by ``hello.bst`` due to the
:ref:`implicit runtime dependency <format_dependencies_types>` introduced by ``base.bst``.

.. tip::

   All of the :ref:`dependencies <format_dependencies>` which are required to run for
   the sake of a build, are staged at the root of the build sandbox. These comprise the
   runtime environment in which the depending element will run commands.

   The result is that the ``make`` program and C compiler provided by ``base/alpine.bst``
   were already in ``$PATH`` and ready to run when the commands were needed by ``hello.bst``.

Now observe that all of the elements in the loaded pipeline are ``cached``,
the element is *built*:

.. raw:: html
   :file: ../sessions/running-commands-show-after.html


Run the hello world program
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Now that we've built everything, we can indulge ourselves in running
the hello world program using :ref:`bst shell <invoking_shell>`:

.. raw:: html
   :file: ../sessions/running-commands-shell.html

Here, :ref:`bst shell <invoking_build>` created a runtime environment for running
the ``hello.bst`` element. This was done by staging all of the dependencies of
``hello.bst`` including the ``hello.bst`` output itself into a directory. Once a directory
with all of the dependencies was staged and ready, we ran the ``hello`` command from
within the build sandbox environment.

.. tip::

   When specifying a command for :ref:`bst shell <invoking_shell>` to run,
   we always specify ``--`` first. This is a commonly understood shell syntax
   to indicate that the remaining arguments are to be treated literally.

   Specifying ``--`` is optional and disambiguates BuildStream's arguments
   and options from those of the program being run by
   :ref:`bst shell <invoking_shell>`.


Summary
-------
In this chapter we've explored how to use the :mod:`manual <elements.manual>` element,
which forms the basis of all build elements.

We've also observed how the directory tree from the output *artifact* of one element
is later *staged* at the root of the sandbox, as input for use by any build elements
which :ref:`depend <format_dependencies>` on that element.

.. tip::

   The way that elements consume their dependency input can vary across the
   different *kinds* of elements. This chapter describes how it works for
   :mod:`build elements <buildstream.buildelement>` implementations, which
   are the most commonly used element type.
