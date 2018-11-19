
.. _examples_out-of-source-build.rst:

Building out of source
======================

Intro
-----

This example aims to:

 * Give a basic overview of how out of source builds can perfomed, tying together
   information spread across different sections of the documentaion that tends to
   group information by element rather than task.
 * Give Examples of how to use out of source builds.
   
Buildstream aims to make out of source builds easy and consistent across as
many build systems as possible. However it should be noted that not all build
systems support `out of source builds`.

Key Variables
-------------

To understand how to perform out od source builds, you must be familier with the
following element properties.

 * ``directory``: Defines the path in the build sandbox at which the element's sources will be staged. This is set for each of the element's sources.
   build root.
 * ``command-subdir`` The working directory used for the element's configure, build and integration commands.
 * ``conf-root`` The path to your build system's configurations file, e.g top level CMakeLists.txt for an element of cmake kind. This path is relative to the elements command-subdir unless is specified as an absolute path.

.. note:

   It is recomended to specify conf-root as an absolute path to make
   life easier if you decide to change command-subdir. Commonly one
   would use a path such as "%{build-root}/Some/Path"

For element kinds which support the above properties, configuring out of source
builds should be as simple as setting them.

 
Examples
--------

The examples shown here can be found in the BuildStream source code in 
``doc/examples/out-of-source`` folder in the BuildStream source. The two cmake
elements we will use as examples are `sourceroot.bst` and `subfolder.bst`.

It is very simple to create a build element that loads a source in to
the `build-root` and then uses the standard build tools to build the
project in the same folder. BuildStream has lots of build element
pluggins so that a new build element may only need to set its `kind`
and then define a source, the `sourceroot.bst` example element takes the
cmake exmaple from the and expands it to a out of source build.

An alternative build elements might build in a sub folder of the source. The
`hello.bst` element in the `autotools` example dose this. And a out of source
version is given in the `subfolder.bst` element of the out of source example
project.


Build project defined in source root
------------------------------------

This example points cmake at the src directory in the root of the source.

In this example, the CMakeLists.txt in the src folder in the root of the source
causes the helloworld program to state that it was build from the root of the 
source project when called.

To make the software build in a folder outside of the source code we set the
source to be in a sub folder of the build-root folder rather than in its root,
in our case this folder will be called ``source``.

The build tools are then set to run a separate folder in the build-root folder,
this will be called ``build``. We must then tell the build tools were to
find the source code, this is done with the ``conf-root`` variable.

This is done by:
 
 * Setting the sources ``directory`` property to ``Source``
 * Setting the element variable ``command-subdir`` to ``build``
 * Setting the element variable ``conf-root`` to ``"%{build-root}/Source/src"``


File: sourceroot.bst
~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/out-of-source-build/elements/sourceroot.bst
   :language: yaml

We can then use the ``bst show`` command to see how variable like ``conf-root``
are expanded.

.. raw:: html
   :file: ../sessions/out-of-source-build-show-variables.html

Build project defined in source subdirectory
--------------------------------------------

This example points cmake at he src/main directory inside the source.

In this example, the CMakeLists.txt in the folder src/main in the root of the
source causes the helloworld program to state that it was build from a subfolder
of the source project when called. 

To make the software build in a folder outside of the source code we set the
source to be in a sub folder of the build-root folder rather than in its root,
in our case this folder will be called ``source``.

The build tools are then set to run a separate folder in the build-root folder,
this will be called ``build``. We must then tell the build tools were to
find the source code, this is done with the ``conf-root`` variable.
Unlike the previous example we need ``conf-root`` to point the sub directory of
the source project rather than the root.



This is done by:
 
 * Setting the sources ``directory`` property to ``Source``
 * Setting the element variable ``command-subdir`` to ``build``
 * Setting the element variable ``conf-root`` to
   ``"%{build-root}/Source/src/main"``

File: subfolder.bst
~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/out-of-source-build/elements/subfolder.bst
   :language: yaml


Run the hello world program
~~~~~~~~~~~~~~~~~~~~~~~~~~~

We can see the output of the two different binaries created from the same
source by invoking the shell of the respective elements with the new programs
name.

When the binary from the build that included the file that defined the extra build
flag ``FULL_PROJECT`` is run, we get the following output:

.. raw:: html
   :file: ../sessions/out-of-source-build-shell.html

When the binary from the build that pointed to the CMakeList.txt that
just adds the source without defining any extra build flags is run, we get the
following output:

.. raw:: html
   :file: ../sessions/out-of-source-build-shell-subfolder.html
