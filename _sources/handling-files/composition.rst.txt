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



.. _handling_files_composition:

Composition
===========
In this chapter we will explore how to create *compositions* of multiple
input filesystem trees, using the :mod:`compose <elements.compose>` element.

.. note::

   This example is distributed with BuildStream
   in the `doc/examples/composition
   <https://github.com/apache/buildstream/tree/master/doc/examples/composition>`_
   subdirectory.


Overview
--------
Composing a directory tree based on a set of build dependencies is often
one of the important steps you might perform in order to create a single artifact
which can be checked out and deployed.

In order to use the :mod:`compose <elements.compose>` element, it is important
to first understand the concept of :ref:`split rules <public_split_rules>`, which
we will cover in this chapter.


Introducing split rules
~~~~~~~~~~~~~~~~~~~~~~~
The :ref:`split rules <public_split_rules>` of an element declaration denote
which sets of files in the given element's resulting artifact belong to which
*domain name*.

The *domains* can then be used in various ways, using plugins which understand
*split rule domains*.

BuildStream's :ref:`default project configuration <project_builtin_defaults>`
contains a sensible set of default *split rule domains* for the purpose of
artifact splitting, they can be overridden in :ref:`your project.conf <project_split_rules>`,
and finally on a per element basis in the :ref:`public data <public_builtin>`
of your element declarations.

.. note::

   Projects are free to add additional *split rule domains* on top of the
   default domains provided by the default project configuration.

   There is nothing wrong with defining split rule domains which *overlap*,
   possibly capturing some of the same files also captured by another
   *domain*, however you should be aware of this when later using your
   split rules with a plugin which processes them, like the
   :mod:`compose <elements.compose>` element described in this chapter.


Example of split rule declaration
'''''''''''''''''''''''''''''''''
In an element, you might need to define or extend the ``split-rules``
in order to capture files in custom locations in a logical *domain*.

Here is an example of how you might use the
:ref:`list append directive <format_directives_list_append>`
to append an additional rule to your ``split-rules`` list in order to
capture additional data files which your application or library might
want to include in the *runtime domain*:

.. code:: yaml

   # Add our .dat files to the runtime domain
   public:
     bst:
       split-rules:
         runtime:
	   (>):
           - |
             %{datadir}/foo/*.dat

Split rules are absolute paths which denote files within an artifact's root
directory. The globbing patterns supported in split rules are defined in the
:func:`reference documentation here <buildstream.utils.glob>`.

.. important::

   Note that because of variable expansion, split rules can often be
   *resolved differently* for elements which have overridden path
   related variables, like ``%{prefix}``.

   This usually means that you do not need to explicitly extend or override
   split rules on a specific element unless your element installs files to
   special case locations.


Project structure
-----------------
In this example we expand on the chapter about
:ref:`integration commands <tutorial_integration_commands>`, so we will
only discuss the files which are added or changed from that example.


``elements/base/alpine.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/composition/elements/base/alpine.bst
   :language: yaml

Here we have modified the base runtime, so as to specify that for this
element, we want to also include the runtime linker into the *runtime domain*.


``elements/runtime-only.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/composition/elements/runtime-only.bst
   :language: yaml

As we can see, this :mod:`compose <elements.compose>` element has
been configured to only include files from the *runtime domain*.


Using the project
-----------------
Now that we've presented how :ref:`split rules <public_split_rules>`
work and shown how to use them in the context of this example, lets
use the :mod:`compose <elements.compose>` element we've created and
observe the results.


Building the project
~~~~~~~~~~~~~~~~~~~~

.. raw:: html
   :file: ../sessions/composition-build.html

As you can see in the output, this composition has only a few hundred
files, but the complete ``alpine.bst`` runtime has several thousand
files.


List the content
~~~~~~~~~~~~~~~~
At the risk of this being a long list, let's :ref:`list the
contents of this artifact <invoking_artifact_list_contents>`

.. raw:: html
   :file: ../sessions/composition-list-contents.html

Some things to observe here:

* The list does include the ``/usr/bin/hello`` program and
  also the ``/usr/lib/libhello.so`` shared library.

  These paths are both captured by the default split rules
  for the *runtime domain*.

* The list does not include the ``/usr/include/libhello.h``
  header file which was used to compile ``/usr/bin/hello``.

  The header file is not captured by the *runtime domain*
  by default. It is however captured by the *devel domain*.

* The runtime linker ``/lib/ld-musl-x86_64.so.1``, as this was
  explicitly added to the *runtime domain* for the ``base/alpine.bst``
  element which provides this file.

.. tip::

   The reader at this time might want to list the content of
   other elements built from this project, such as the
   ``hello.bst`` element by itself, or the ``base/alpine.bst``
   element.


Run the program
~~~~~~~~~~~~~~~
Finally, lets just run the program we built.

.. raw:: html
   :file: ../sessions/composition-shell.html

Here we can see that we at least have the required files to run
our hello world program, however we would not have if we were
missing the runtime linker which we added in ``base/alpine.bst``.


Summary
-------
In this chapter we've gotten familiar with :ref:`split rules <public_split_rules>`
annotations, and we've learned enough about the :mod:`compose <elements.compose>`
element such that we can start creating our own compositions using
*split domains*.

We've also used the :ref:`list append directive <format_directives_list_append>`
and we are now observing the contents of artifacts using
:ref:`bst artifact list-contents <invoking_artifact_list_contents>`.
