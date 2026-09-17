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



.. _tutorial_directives:

Optionality and directives
==========================
In this chapter we're going to go over some of the more flexible constructs
which BuildStream offers for :ref:`optionality <project_options>`, and
show how we can use :ref:`directives <format_directives>` in the BuildStream
YAML format.

.. note::

   This example is distributed with BuildStream
   in the `doc/examples/directives
   <https://github.com/apache/buildstream/tree/master/doc/examples/directives>`_
   subdirectory.


Overview
--------
This chapter's example will build another ``hello.c`` program which much
resembles the program in the :ref:`running commands <tutorial_running_commands>` example,
but here we're going to make the greeting string *configurable* using the C
preprocessor.

We'll be compiling the following C file:


``files/src/hello.c``
~~~~~~~~~~~~~~~~~~~~~
.. literalinclude:: ../../examples/directives/files/src/hello.c
   :language: c

And we're going to build it using ``make``, using the following Makefile:


``files/src/Makefile``
~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/directives/files/src/Makefile
   :language: Makefile

Notice the addition of ``-DGREETING_MESSAGE="\"${GREETING}\""`` in the above
Makefile, this will allow us to configure the greeting message from the
``hello.bst`` element declaration.

We will need to add support to our project for *optionality*, and we'll
have to make *conditional statements* to resolve what kind of greeting
we want from the hello world program.


Project structure
-----------------
Since this project has much the same structure as the
:ref:`running commands <tutorial_running_commands>` chapter did, we won't go over all of
these elements in detail. Instead let's focus on the addition of the new
:ref:`project options <project_options>` in ``project.conf``, the added
file in the ``include/`` project subdirectory, and how these come together
in the the ``hello.bst`` element.


``project.conf``
~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/directives/project.conf
   :language: yaml

Here, our ``project.conf`` declares a project option called ``flavor``, and this
will inform what kind of greeting message we want to use when building the project.


``elements/hello.bst``
~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/directives/elements/hello.bst
   :language: yaml

Notice the ``(@)`` symbol we've added in the ``variables:`` section, this
symbol is used to invoke the :ref:`include directive <format_directives_include>`,
which can be useful for code sharing between elements or simply to improve readability.

In this case, we are compositing the content of ``include/greeting.bst`` into the
:ref:`variables <format_variables>` section of the element declaration, directives
can however be used virtually anywhere in the BuildStream YAML format.


``include/greeting.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/directives/include/greeting.bst
   :language: yaml

Here we can see the dictionary which will be composited into the ``variables:``
section of the ``hello.bst`` element described above.

Note the usage of the ``(?)`` symbol at the toplevel of the YAML dictionary,
this is how we perform :ref:`conditional statements <format_directives_conditional>`
in the BuildStream YAML format.

This include file uses the ``flavor`` project option we declared in ``project.conf`` to
decide what value will end up being assigned to the ``%{greeting}`` variable, which
will ultimately be used in the ``hello.bst`` element.


Using the project
-----------------
Now that we have a project which uses options and conditional statements,
lets build the project with a few different options and observe the outputs.


Building hello.bst element with options
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Since the :ref:`flavor option <project_options>` we've declared above
has a default, we can build it the first time using :ref:`bst build <invoking_build>`
without any special command line options:

.. raw:: html
   :file: ../sessions/directives-build-normal.html

If we want to build the ``somber`` flavor, we just need to specify the
additional ``--option`` command line option to :ref:`bst <invoking_bst>`
in order to inform BuildStream of the options we want.

.. raw:: html
   :file: ../sessions/directives-build-somber.html

Note that the ``--option`` option can be specified many times on the
``bst`` command line, so as to support projects which have multiple
options.

Finally lets get the ``excited`` flavor built as well:

.. raw:: html
   :file: ../sessions/directives-build-excited.html

If you observe the cache keys above, you will notice that while
we have only three elements in the pipeline, counting ``base/alpine.bst``,
``base.bst`` and ``hello.bst``, we have actually built *five artifacts*,
because the ``hello.bst`` is built differently each time, it has a
different cache key and is stored separately in the artifact cache.


Run the hello world program with options
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Since the ``--option`` command line option to :ref:`bst <invoking_bst>`
is a main option, it can be used in any command.

Let's run the ``hello`` program using :ref:`bst shell <invoking_shell>`
three times in a row, each time using a different option so we can
observe the results.


.. raw:: html
   :file: ../sessions/directives-shell-normal.html


.. raw:: html
   :file: ../sessions/directives-shell-somber.html


.. raw:: html
   :file: ../sessions/directives-shell-excited.html


Summary
-------
In this chapter we've demonstrated how to declare :ref:`project options <project_options>`,
how to use :ref:`conditional directives <format_directives_conditional>`, and also
how to use :ref:`include directives <format_directives_include>`.

To get more familliar with these concepts, you may want to explore the remaining
:ref:`directives <format_directives>` in the BuildStream YAML format, and also take
a look at the various :ref:`types of project options <project_options>` that
are also supported.
