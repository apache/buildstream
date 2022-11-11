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



.. _handling_files_filtering:

Filtering
=========
In this chapter we will explore how to *filter* the files in an artifact
using the :mod:`filter <elements.filter>` element, such that an element might
depend on a subset of the files provided by a filtered element.

.. note::

   This example is distributed with BuildStream
   in the `doc/examples/filtering
   <https://github.com/apache/buildstream/tree/master/doc/examples/filtering>`_
   subdirectory.


Overview
--------
In some cases, it can be useful to depend on a *subset* of the files of an
element, without depending on the entire element.

One scenario where filtering can be useful, is when you have an element which
will build differently depending on what is present in the system where it is
building. In an edge case where a module fails to offer configure time options to
disable an unwanted feature or behavior in the build, you might use
:mod:`filter <elements.filter>` elements to ensure that special header files or
pkg-config files are *filtered out* from the system at build time, such that
the unwanted behavior cannot be built.

In many ways, a :mod:`filter <elements.filter>` element is like a
:mod:`compose <elements.compose>` element, except that it operates on a single
:ref:`build dependency <format_build_depends>`, without compositing the filtered
element with its :ref:`runtime dependencies <format_runtime_depends>`.

.. tip::

   The :mod:`filter <elements.filter>` element is special in the sense
   that it acts as a *window* into it's primary
   :ref:`build dependency <format_build_depends>`.

   As such, :ref:`opening a workspace <invoking_workspace_open>` on a
   :mod:`filter <elements.filter>` element will result in opening a
   workspace on the element which it filters. Any other workspace
   commands will also be forwarded directly to the filtered element.


Project structure
-----------------
This example again expands on the example presenting in the chapter about
:ref:`integration commands <tutorial_integration_commands>`. In this case
we will modify ``libhello.bst`` such that it produces a new file which,
if present, will affect the behavior of it's reverse dependency ``hello.bst``.

Let's first take a look at how the sources have changed.


``files/hello/Makefile``
~~~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/filtering/files/hello/Makefile
   :language: Makefile

Now we have our Makefile discovering the system defined default
person to say hello to.


``files/hello/hello.c``
~~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/filtering/files/hello/hello.c
   :language: c

If this program has been given a ``DEFAULT_PERSON``, then it will
say hello to that person in the absence of any argument.


``project.conf``
~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/filtering/project.conf
   :language: yaml

Here, we've added a :ref:`project option <project_options>` to decide
whether to use the :mod:`filter <elements.filter>` element or not.

This is merely for brevity, so that we can demonstrate the behavior
of depending on the filtered element without defining two separate versions
of the ``hello.bst`` element.


``elements/libhello.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/filtering/elements/libhello.bst
   :language: yaml

We've added some :ref:`split rules <public_split_rules>` here to declare
a new *split domain* named ``defaults``, and we've added the new
``default-person.txt`` file to this *domain*.


``elements/libhello-filtered.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/filtering/elements/libhello-filtered.bst
   :language: yaml

And we've added a new :mod:`filter <elements.filter>` element to the project
which uses the ``exclude`` option of the filter configuration.

This is essentially a statement that any files mentioned in the the
``defaults`` *domain* of the ``libhello.bst`` element should be excluded from
the resulting artifact.

.. important::

   Notice that you need to explicitly declare any
   :ref:`runtime dependencies <format_runtime_depends>` which are required by the
   resulting artifact of a :mod:`filter <elements.filter>` element, as runtime
   dependencies of the build dependency are not transient.


``elements/hello.bst``
~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/filtering/elements/hello.bst
   :language: yaml

Here we've merely added a :ref:`conditional statement <format_directives_conditional>`
which allows us to test the ``hello.bst`` element depending on the filtered
version of the library, or the unfiltered version.


Using the project
-----------------
Let's just skip over building the ``hello.bst`` element with the
``use_filter`` option both ``True`` and ``False``, these elements
are easily built with :ref:`bst build <invoking_build>` as such:

.. code:: shell

   bst --option use_filter True build hello.bst
   bst --option use_filter False build hello.bst


Observing the artifacts
~~~~~~~~~~~~~~~~~~~~~~~
Let's take a look at the built artifacts.


``libhello.bst``
''''''''''''''''

.. raw:: html
   :file: ../sessions/filtering-list-contents-libhello.html

Here we can see the full content of the ``libhello.bst`` artifact.


``libhello-filtered.bst``
'''''''''''''''''''''''''

.. raw:: html
   :file: ../sessions/filtering-list-contents-libhello-filtered.html

Here we can see that the ``default-person.txt`` file has been filtered
out of the ``libhello.bst`` artifact when creating the ``libhello-filtered.bst``
artifact.


Running hello.bst
~~~~~~~~~~~~~~~~~
Now if we run the program built by ``hello.bst`` in either build
modes, we can observe the expected behavior.


Run ``hello.bst`` built directly against ``libhello.bst``
'''''''''''''''''''''''''''''''''''''''''''''''''''''''''

.. raw:: html
   :file: ../sessions/filtering-shell-without-filter.html

Here we can see that the hello world program is using the system
configured default person to say hello to.


Run ``hello.bst`` built against ``libhello-filtered.bst``
'''''''''''''''''''''''''''''''''''''''''''''''''''''''''

.. raw:: html
   :file: ../sessions/filtering-shell-with-filter.html

And now we're reverting to the behavior we have when no
system configured default person was installed at build time.


Summary
-------
In this chapter, we've introduced the :mod:`filter <elements.filter>`
element which allows one to filter the output of an element and
effectively create a dependency on a subset of an element's files.
