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



.. _tutorial_integration_commands:

Integration commands
====================
Sometimes a software requires more configuration or processing than what is
performed at installation time, otherwise it will not run properly.

This is especially true in cases where a daemon or library interoperates
with third party extensions and needs to maintain a system wide cache whenever
its extensions are installed or removed; system wide font caches are an example
of this.

In these cases we use :ref:`integration commands <public_integration>` to
ensure that a runtime is ready to run after all of its components have been *staged*.

.. note::

   This example is distributed with BuildStream
   in the `doc/examples/integration-commands
   <https://github.com/apache/buildstream/tree/master/doc/examples/integration-commands>`_
   subdirectory.


Overview
--------
In this chapter, we'll be exploring :ref:`integration commands <public_integration>`,
which will be our first look at :ref:`public data <format_public>`.


Project structure
-----------------


``project.conf`` and  ``elements/base.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The project.conf and base stack :mod:`stack <elements.stack>` element are configured in the
same way as in the previous chapter: :ref:`tutorial_running_commands`.


``elements/base/alpine.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/integration-commands/elements/base/alpine.bst
   :language: yaml

This is the same ``base/alpine.bst`` we've seen in previous chapters,
except that we've added an :ref:`integration command <public_integration>`.

This informs BuildStream that whenever the output of this element is
expected to *run*, this command should be run first. In this case we
are simply running ``ldconfig`` as a precautionary measure, to ensure
that the runtime linker is ready to find any shared libraries we may
have added to ``%{libdir}``.


Looking at public data
''''''''''''''''''''''
The :ref:`integration commands <public_integration>` used here is the first time
we've used any :ref:`builtin public data <public_builtin>`.

Public data is a free form portion of an element's configuration and
is not necessarily understood by the element on which it is declared, public
data is intended to be read by its reverse dependency elements.

This allows annotations on some elements to inform elements later in
the dependency chain about details of its artifact, or to suggest how
it should be processed.


``elements/libhello.bst`` and  ``elements/hello.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
These are basically manual elements very similar to the ones we've
seen in the previous chapter: :ref:`tutorial_running_commands`.

These produce a library and a hello program which uses the library,
we will consider these irrelevant to the topic and leave examination
of `their sources
<https://github.com/apache/buildstream/tree/master/doc/examples/integration-commands/files>`_
as an exercise for the reader.


Using the project
-----------------


Build the hello.bst element
~~~~~~~~~~~~~~~~~~~~~~~~~~~
To build the project, run :ref:`bst build <invoking_build>` in the
following way:

.. raw:: html
   :file: ../sessions/integration-commands-build.html

Observe in the build process above, the integration command declared on the
``base/alpine.bst`` element is run after staging the dependency artifacts
into the build sandbox and before running any of the build commands, for
both of the ``libhello.bst`` and ``hello.bst`` elements.

BuildStream assumes that commands which are to be run in the build sandbox
need to be run in an *integrated* sandbox.

.. tip::

   Integration commands can be taxing on your overall build process,
   because they need to run at the beginning of every build which
   :ref:`runtime depends <format_dependencies_types>` on the element
   declaring them.

   For this reason, it is better to leave out more onerous tasks
   if they are not needed at software build time, and handle those
   specific tasks differently later in the pipeline, before deployment.


Run the hello world program
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unlike the previous chapters, this hello world program takes an argument,
we can invoke the program using :ref:`bst shell <invoking_shell>`:

.. raw:: html
   :file: ../sessions/integration-commands-shell.html

Here we see again, the integration commands are also used when preparing
the shell to launch a command.


Summary
-------
In this chapter we've observed how :ref:`integration commands <public_integration>`
work, and we now know about :ref:`public data <format_public>`, which plugins
can read from their dependencies in order to influence their build process.
