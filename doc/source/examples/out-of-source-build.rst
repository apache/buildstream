
.. _examples_out-of-source-build.rst:

Building out of source
======================

Intro
-----

This example aims to show:

 * Give a basic overview of how out of source builds can work tying together
   bits of information spread across different sections of the docs that tend to
   group information by element rather than task.
 * Give Examples of how to use out of source builds.
   
Buildstream aims to make out of source builds easy and consistent, across as
many build systems as possible. However it should be noted that not all build
systems support `out of source builds`.

Key Variables
-------------

Out of source builds are configured by setting:
 
 * ``directory`` of the source, this sets the source to open in to a folder in the
   build root.
 * ``command-subdir`` variable, sets were the build will be run.
 * ``conf-root`` variable, tells the configuration tool were to find the root of
   the source code.
   
``conf-root`` is given to the configuration tool which is run in
``command-subdir``. It can ether be given as a relative path from 
``command-subdir`` to the location of the source code. Or as an absolute
location.

By setting ``conf-root`` as a absolute path we can change ``command-subdir``
with out having to change ``conf-root``.

If a absolute path is given it must be from the root of the sandbox.
To specify a absolute path from the root of the build-root the build-root
variable can be used eg. ``conf-root`` can be set to ``"%{build-root}/Source"``
to specify the ``Source`` folder in the root of the build-root.

These variables can be use for many of the buildstream build element kinds.
Indeed converting to out of source builds should be as simple as adding these
variables to the individual bst files and in some circumstance most of the
variables could be set at a project level.

 
Examples
--------

The out of source examples can be found in the buildstream source code in 
``doc/examples/out-of-source`` folder in the buildstream source. The two cmake
elements we will use as examples are `sourceroot.bst` and `subfolder.bst`.

It is very simple to create a build element that loads a source in to the
`build-root` and then uses the standard build tools to build the project in the
same folder. Buildstream has lots of build element plugs so that a new element
may only need to set its `kind` to the relevant build system and then define a
source, the `sourceroot.bst` example element takes a cmake exmaple and expands
it to a out of source build.

An alternative build elements might build in a sub folder of the source. The
`hello.bst` element in the `autotools` example dose this. And a out of source
version is given in the `subfolder.bst` element of the out of source example
project.


Build project defined in source root
------------------------------------

This example points cmake at the src directory in the root of the source.

In this example, the CMakeLis.txt in the src folder in the root of the source
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

In this example, the CMakeLis.txt in the folder src/main in the root of the
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
